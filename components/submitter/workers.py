import asyncio
from submission import prepare_submission_data
from sqlalchemy import create_engine, select, text, func, literal
from sqlalchemy.orm import sessionmaker
from db import Bug, BugGroup, Task, Patch, BugProfile, PatchBug, PatchStatus, SarifResult, Sarif, BugProfileStatus, PatchSubmit
from db import SubmissionStatusEnum
import logging
import json
from tasks import submit_data_task, confirm_submission_task, bundle_submission_task
import time
import traceback

async def fetch_data(db_engine, msg_set, redisstore):
    # engine = create_engine(db_url)
    session = sessionmaker(bind = db_engine)()
    
    # get all the running tasks
    stmt = (
        select (
            Task.id, 
        # TODO: change this to status == "processing"
        ).where(Task.status == "processing")
    )
    task_list = session.execute(stmt).scalars().all()
    session.commit()
    
    logging.info(f"Found {len(task_list)} tasks that are processing")
    logging.debug(f"Task list: {task_list}")
    
    # select bug
    stmt = (
        select(
            Bug,
            BugGroup.bug_profile_id
        )
        .join(BugGroup, Bug.id == BugGroup.bug_id)
        .where(Bug.task_id.in_(task_list))
        .order_by(BugGroup.bug_profile_id, Bug.id)
        .distinct(BugGroup.bug_profile_id)
    )
    
    bugs = session.execute(stmt).all()
    session.commit()

    logging.info(f"Found {len(bugs)} bugs to submit")
    # logging.debug(f"Bug list: {bugs}")
    
    lock = asyncio.Lock()

    for bug_res in bugs:
        bug = bug_res[0]
        bug_profile_id = bug_res[1]
        async with lock:
            data = await redisstore.get(f"submitter:pov:{bug.task_id}:{bug.id}:{bug_profile_id}")
            bug_profile = await redisstore.get(f"submitter:bug_profile:{bug_profile_id}")
        if data is not None or bug_profile is not None:
            logging.info(f"POV task for bug {bug.id} / bug_profile {bug_profile_id} already submitted")
            continue
        try:
            pov_submission_data = prepare_submission_data("pov", bug)
        except Exception as e:
            logging.error(f"Error in prepare_submission_data: {e}")
            continue
        # data_hash = hashlib.sha256(json.dumps(pov_submission_data).encode()).hexdigest()
        # submit pov task to redis
        logging.info(f"Submitting pov task for bug {bug.id}, bug profile id {bug_profile_id}")
        logging.debug(f"POV submission data: {pov_submission_data}")
        async with lock:
            await redisstore.set(f"submitter:pov:{bug.task_id}:{bug.id}:{bug_profile_id}", json.dumps(pov_submission_data))
            await redisstore.set(f"submitter:bug_profile:{bug_profile_id}", "submitted")
            if await redisstore.get(f"submitter:pov:{bug.task_id}:{bug.id}:{bug_profile_id}") is None:
                logging.error(f"Failed to submit pov task for bug {bug.id}, bug profile id {bug_profile_id}")
                continue
            await msg_set.add(f"submitter:pov:{bug.task_id}:{bug.id}:{bug_profile_id}")
        # print(bug.id)
    
    # select patch 
    # stmt = (
    #     select(
    #         Patch,
    #         BugProfile.task_id
    #     )
    #     .join(BugProfile, Patch.bug_profile_id == BugProfile.id)
    #     .where(BugProfile.task_id.in_(task_list))
    #     .order_by(Patch.bug_profile_id, Patch.id)
    #     .distinct(Patch.bug_profile_id)
    # )

    # NEEDS IMPROVEMENT: very complicated query, need to optimize

    async with lock:
        # select all confirmed bugs
        stmt = (
            select(
                BugProfileStatus.bug_profile_id
            )
            .where(
                BugProfileStatus.status == SubmissionStatusEnum.passed
            )
            .distinct()
        )
        confirmed_bugs = session.execute(stmt).scalars().all()
        session.commit()
        logging.info(f"Found {len(confirmed_bugs)} confirmed bugs")

    #     unrepaired_patches = (
    #         select(PatchBug.patch_id)
    #         .where(PatchBug.repaired == False)
    #         .distinct(PatchBug.patch_id)
    #     ).subquery()

    #     # Subquery to get distinct bug profiles.
    #     # Update: only select the bug profiles that have already been submitted and confirmed correct
    #     distinct_bug_profiles = (
    #         select(BugProfile.id)
    #         .where(BugProfile.task_id.in_(task_list),
    #                BugProfile.id.in_(confirmed_bugs)
    #         )
    #         .distinct()
    #     ).subquery()

    #     # Lateral subquery: for each distinct bug profile, select up to 2 patch IDs.
    #     lateral_subq = (
    #         select(
    #             Patch.id.label("patch_id"),
    #             BugProfile.task_id
    #         )
    #         .join(BugProfile, Patch.bug_profile_id == BugProfile.id)
    #         .where(
    #             Patch.id.not_in(select(unrepaired_patches)),
    #             BugProfile.id == distinct_bug_profiles.c.id
    #         )
    #         .order_by(Patch.bug_profile_id, Patch.id)
    #         .limit(2)
    #         .lateral()
    #     )

    #     # Outer query: join the lateral subquery with the Patch ORM model so we return ORM objects.
    #     stmt = (
    #         select(
    #             Patch,
    #             lateral_subq.c.task_id,
    #         )
    #         .select_from(
    #             distinct_bug_profiles
    #             .join(lateral_subq, literal(True))
    #             .join(Patch, Patch.id == lateral_subq.c.patch_id)
    #         )
    #         .order_by(Patch.bug_profile_id, Patch.id)
    #     )


    #     patches = session.execute(stmt).all()
    #     session.commit()

    #     logging.info(f"Found {len(patches)} patches to submit")
    #     # print(str(patches[0]))
        stmt = (
            select(
                PatchStatus.patch_id
            )
            .where(PatchStatus.functionality_tests_passing != True)
        )

        failed_patches = session.execute(stmt).scalars().all()
        session.commit()
        logging.debug(f"Func test failed patches: {failed_patches}")
        # logging.debug(f"Patch list: {patches}")


    # # group patches by bug profile id
    # patches_by_bug_profile = {}
    # for patch_res in patches:
    #     patch = patch_res[0]
    #     task_id = patch_res[1]
    #     if patch.bug_profile_id not in patches_by_bug_profile:
    #         patches_by_bug_profile[patch.bug_profile_id] = []
    #     patches_by_bug_profile[patch.bug_profile_id].append((patch, task_id))

    # # only select the first non-failed patch for each bug profile
    # submission_list = []
    # for bug_profile_id in patches_by_bug_profile:
    #     for i in range(len(patches_by_bug_profile[bug_profile_id])):
    #         patch = patches_by_bug_profile[bug_profile_id][i][0]
    #         task_id = patches_by_bug_profile[bug_profile_id][i][1]
    #         if patch.id not in failed_patches:
    #             submission_list.append((patch, task_id))
    #             break

        stmt = (
            select(
                Patch,
                BugProfile.task_id,
                PatchSubmit.patch_id,
            )
            .join(Patch, PatchSubmit.patch_id == Patch.id)
            .join(BugProfile, BugProfile.id == Patch.bug_profile_id)
            .where(
                BugProfile.task_id.in_(task_list),
                PatchSubmit.patch_id.not_in(failed_patches),
                BugProfile.id.in_(confirmed_bugs)
            )
        )

        patch_submits = session.execute(stmt).all()
        session.commit()
        logging.info(f"Found {len(patch_submits)} patch submits")
        logging.debug(f"Patch submit list: {patch_submits}")
        submission_list = []
        for patch_submit in patch_submits:
            submission_list.append(patch_submit)
    
    logging.info(f"Submitting {len(submission_list)} patches")
    logging.debug(f"Submission list: {submission_list}")

    for patch_res in submission_list:
        patch = patch_res[0]
        task_id = patch_res[1]
        if patch.id in failed_patches:
            logging.info(f"Patch {patch.id} has already failed, skipping")
            continue
        async with lock:
            data = await redisstore.get(f"submitter:patch:{task_id}:{patch.id}:{patch.bug_profile_id}")
        if data is not None:
            logging.info(f"Patch task for bug {patch.id} already submitted")
            continue

        try:
            patch_submission_data = prepare_submission_data("patch", patch)
        except Exception as e:
            logging.error(f"Error in prepare_submission_data: {e}")
            continue
        logging.info(f"Submitting patch task for bug {patch.id}, task {task_id}")
        logging.debug(f"Patch submission data: {patch_submission_data}")
        async with lock:
            await redisstore.set(f"submitter:patch:{task_id}:{patch.id}:{patch.bug_profile_id}", json.dumps(patch_submission_data))
            if await redisstore.get(f"submitter:patch:{task_id}:{patch.id}:{patch.bug_profile_id}") is None:
                logging.error(f"Failed to submit patch task for bug {patch.id}")
                continue
            await msg_set.add(f"submitter:patch:{task_id}:{patch.id}:{patch.bug_profile_id}")
        # print(patch.id)
    # logging.debug(f"Patch list: {patches}")

    # select sarif report
    stmt = (
        select(
            SarifResult
        ).where(
            SarifResult.task_id.in_(task_list),
        )
    )
    
    sarifs = session.execute(stmt).scalars().all()
    session.commit()
    logging.info(f"Found {len(sarifs)} sarif reports to submit")
    # logging.debug(f"Sarif list: {sarifs}")
    for sarif in sarifs:
        async with lock:
            data = await redisstore.get(f"submitter:sarif:{sarif.task_id}:{sarif.sarif_id}:{sarif.bug_profile_id}")
        if data is not None:
            logging.info(f"Sarif assessment {sarif.sarif_id} already submitted")
            continue
        try:
            sarif_submission_data = prepare_submission_data("sarif", sarif)
        except Exception as e:
            logging.error(f"Error in prepare_submission_data: {e}")
            continue
        logging.info(f"Submitting sarif {sarif.sarif_id}, task {sarif.task_id}")
        logging.debug(f"Sarif submission data: {sarif_submission_data}")
        async with lock:
            await redisstore.set(f"submitter:sarif:{sarif.task_id}:{sarif.sarif_id}:{sarif.bug_profile_id}", json.dumps(sarif_submission_data))
            if await redisstore.get(f"submitter:sarif:{sarif.task_id}:{sarif.sarif_id}:{sarif.bug_profile_id}") is None:
                logging.error(f"Failed to submit sarif {sarif.sarif_id}")
                continue
            await msg_set.add(f"submitter:sarif:{sarif.task_id}:{sarif.sarif_id}:{sarif.bug_profile_id}")
    
    
    session.close()

async def db_worker(db_engine, msgqueue, redisstore, interval):
    while True:
        current_time = time.time()
        try:
            await fetch_data(db_engine, msgqueue, redisstore)
        except Exception as e:
            logging.error(f"Error in db_worker: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")
        elapsed_time = time.time() - current_time
        logging.info(f"Elapsed time: {elapsed_time}")
        await asyncio.sleep(interval - elapsed_time)
        
    

async def submit_worker(base_url, msgqueue, confirm_queue, redisstore):
    while True:
        try:
            await submit_data_task(base_url, msgqueue, confirm_queue, redisstore)
        except Exception as e:
            logging.error(f"Error in submit_worker: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")

async def confirm_worker(base_url, confirm_queue, db_engine, bundle_queue, redisstore, task_queue):
    # engine = create_engine(db_url)
    db_session = sessionmaker(bind = db_engine)()
    while True:
        try:
            for i in range(5):
                try:
                    db_session.execute(text("SELECT 1"))
                    # db_session.commit()
                    break
                except Exception as e:
                    logging.warning(f"Database connection lost: {e}, reconnecting {i+1}")
                    await asyncio.sleep(1)
                    db_session = sessionmaker(bind = db_engine)()
            await confirm_submission_task(base_url, confirm_queue, db_session, bundle_queue, redisstore, task_queue)
            await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"Error in confirm_worker: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")

async def bundle_worker(base_url, bundle_queue, redisstore):
    while True:
        try:
            await bundle_submission_task(base_url, bundle_queue, redisstore)
            # await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"Error in bundle_worker: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")