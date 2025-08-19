import asyncio
from submission import prepare_submission_data, submit_data, confirm_submission
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from db import BugProfileStatus, PatchStatus
import logging
from otlp import log_action, get_task_metadata, telemetry_spans, create_span, mark_span_failed, end_span, SpanContextManager
import json

async def submit_data_task(base_url, task_set, confirm_set, redisstore):
    lock = asyncio.Lock()
    async with lock:
        task = await task_set.get_one()
        if task is None:
            return
        data = await redisstore.get(task)
    if data is None:
        return 
    _, task_type, task_id, id, bug_profile_id = task.decode().split(":")
    metadata = await get_task_metadata(redisstore, task_id)
    logging.info(f"Submitting {task_type} {id} for task {task_id}")
    
    attributes = {
        "crs.action.category": "scoring_submission",
        "crs.action.name": "submit_final_results",
    } 
    for key, value in metadata.items():
        attributes[key] = value
    
    span_id = f"submitter:{task_type}:{task_id}:{id}:{bug_profile_id}:start"
    root_span = create_span(f"Submitter: Submit {task_type}", attributes)
    current_spans = telemetry_spans.get()
    current_spans[span_id] = root_span
    telemetry_spans.set(current_spans)
    
    submit_data_span = create_span(f"Submitter: Submit {task_type} data", attributes, parent_span=root_span)
    
    result = submit_data(base_url, task_type, task_id, data, sarif_id = id)
    if result["status"] == "accepted" or result["status"] == "inconclusive":
        if task_type != "sarif":
            submission_id = result[f"{task_type}_id"]
            logging.info(f"Submitted {task_type} {id} for task {task_id}, got submission id {submission_id}")
        else:
            logging.info(f"Submitted sarif report for task {task_id}, sarif id {id}")
        async with lock:
            if task_type != "sarif":
                await confirm_set.add(f"submitter:{task_type}:{task_id}:{id}:{submission_id}:{bug_profile_id}")
            await task_set.remove(task)
        end_span(submit_data_span)
    elif result["status"] == "deadline_exceeded":
        logging.error(f"Failed to submit {task_type} {id} for task {task_id}: deadline exceeded")
        async with lock:
            await task_set.remove(task)
        mark_span_failed(submit_data_span, Exception("Deadline exceeded"))
        end_span(submit_data_span)
        mark_span_failed(root_span, Exception("Deadline exceeded"))
        end_span(root_span)
    else:
        logging.error(f"Failed to submit {task_type} {id} for task {task_id}: {result["status"]}")
        mark_span_failed(submit_data_span, Exception(f"Failed to submit {task_type} {id} for task {task_id}: {result["status"]}"))
        end_span(submit_data_span)
        mark_span_failed(root_span, Exception(f"Failed to submit {task_type} {id} for task {task_id}: {result["status"]}"))
        end_span(root_span)
        
        

async def confirm_submission_task(base_url, confirm_set, db_session, bundle_set, redisstore, task_set):
    lock = asyncio.Lock()
    async with lock:
        task = await confirm_set.get_one()
    if task is None:
        return 
    _, task_type, task_id, id, submission_id, bug_profile_id = task.decode().split(":")
    metadata = await get_task_metadata(redisstore, task_id)
    
    attributes = {
        "crs.action.category": "scoring_submission",
        "crs.action.name": "submit_final_results",
    } 
    for key, value in metadata.items():
        attributes[key] = value
    
    # get root span from telemetry_spans
    span_id = f"submitter:{task_type}:{task_id}:{id}:{bug_profile_id}:start"
    root_span = telemetry_spans.get()[span_id]
    
    
    confirm_span_id = f"submitter:{task_type}:{task_id}:{id}:{submission_id}:{bug_profile_id}:confirm"
    if confirm_span_id in telemetry_spans.get():
        confirm_span = telemetry_spans.get()[confirm_span_id]
    else:
        confirm_span = create_span(f"Submitter: Confirm {task_type}", attributes, parent_span=root_span)
        current_spans = telemetry_spans.get()
        current_spans[confirm_span_id] = confirm_span
        telemetry_spans.set(current_spans)
    
    
    
    logging.info(f"Confirming {task_type} {id} for task {task_id}, submission id {submission_id}")
    result = confirm_submission(base_url, task_type, task_id, submission_id)
    confirm_span.add_event(f"Confirming {task_type} {id} for task {task_id}, submission id {submission_id}")
    if task_type == "patch":
        # special usage for patch
        if (("functionality_tests_passing" not in result) or (result["functionality_tests_passing"] is None)) and (result["status"] == "accepted" or result["status"] == "inconclusive"):
            logging.info(f"Still waiting for confirmation for patch {id} of task {task_id}")
        else:
            if "functionality_tests_passing" not in result:
                func_test_result = None
            else:
                func_test_result = result["functionality_tests_passing"] 
            logging.info(f"Patch {id} of task {task_id} has been confirmed: status {result["status"]} func test {func_test_result}")
            status = result["status"]
            async with lock:
                # update information to database
                # engine = create_engine(db_url)
                # session = sessionmaker(bind = engine)()
                patch_status = PatchStatus(
                    patch_id = int(id),
                    status = status,
                    functionality_tests_passing = func_test_result
                )
                db_session.add(patch_status)
                db_session.commit()
                await confirm_set.remove(task)

                # bundle submission: if func test pass, submit bundle
                if func_test_result == True:
                    logging.info(f"Patch {id} of task {task_id} passed functionality tests, submitting bundle, repairing bug profile {bug_profile_id}")
                    await redisstore.set(f"submitter:bundle:patch:{bug_profile_id}", submission_id)
                    # currently, we only assign 1 bundle for 1 patch and 1 pov
                    await bundle_set.add(f"submitter:bundle:{task_id}:{bug_profile_id}")
                    end_span(confirm_span)
                    end_span(root_span)
                else:
                    # func test failed
                    mark_span_failed(confirm_span, Exception("Functionality tests failed"))
                    end_span(confirm_span)
                    mark_span_failed(root_span, Exception("Functionality tests failed"))
                    end_span(root_span)


            # opentelemetry log
            


        
    elif task_type == "pov":
        if result["status"] == "accepted":
            logging.info(f"Still waiting for confirmation for {task_type} {id} of task {task_id}")
        elif result["status"] == "errored":
            # revert to the old status
            logging.error(f"Got a server side error of {task_type} {id} of task {task_id}. Need to resubmit")
            val = f"submitter:pov:{task_id}:{id}:{bug_profile_id}"
            async with lock:
                await confirm_set.remove(task)
                await task_set.add(val)
            mark_span_failed(confirm_span, Exception("Server side error"))
            end_span(confirm_span)
            mark_span_failed(root_span, Exception("Server side error"))
            end_span(root_span)
        else:
            logging.info(f"{task_type} {id} of task {task_id} has been confirmed: {result["status"]}")
            async with lock:
                # update information to database
                # engine = create_engine(db_url)
                # session = sessionmaker(bind = engine)()
                pov_status = BugProfileStatus(
                    bug_profile_id = int(bug_profile_id),
                    status = result["status"]
                )
                db_session.add(pov_status)
                db_session.commit()
                await confirm_set.remove(task)

                # set the pov submission id to redis, for bundle submission
                if result["status"] == "passed":
                    await redisstore.set(f"submitter:bundle:bug_profile:{bug_profile_id}", submission_id)
                    end_span(confirm_span)
                    end_span(root_span)
                else:
                    mark_span_failed(confirm_span, Exception(f"{task_type} {id} of task {task_id} has been confirmed: {result["status"]}"))
                    end_span(confirm_span)
                    mark_span_failed(root_span, Exception(f"{task_type} {id} of task {task_id} has been confirmed: {result["status"]}"))
                    end_span(root_span)
            
            # opentelemetry log
            


    else:
        if result["status"] == "accepted":
            logging.info(f"Still waiting for confirmation for {task_type} {id} of task {task_id}")
        else:
            logging.info(f"{task_type} {id} of task {task_id} has been confirmed: {result["status"]}")
            async with lock:
                await confirm_set.remove(task)
            end_span(confirm_span)
            end_span(root_span)


async def bundle_submission_task(base_url, bundle_queue, redisstore):
    lock = asyncio.Lock()
    async with lock:
        task = await bundle_queue.get_one()
        if task is None:
            return
        _, _, task_id, bug_profile_id = task.decode().split(":")
        # at least we need a pov and a patch to submit a bundle
        pov_uuid = await redisstore.get(f"submitter:bundle:bug_profile:{bug_profile_id}")
        pov_uuid = pov_uuid.decode() if pov_uuid is not None else None
        patch_uuid = await redisstore.get(f"submitter:bundle:patch:{bug_profile_id}")
        patch_uuid = patch_uuid.decode() if patch_uuid is not None else None
    if pov_uuid is None or patch_uuid is None:
        return 
    # _, task_id, id = task.decode().split(":")
    logging.info(f"Submitting bundle for task {task_id}, pov {pov_uuid}, patch {patch_uuid}")
    metadata = await get_task_metadata(redisstore, task_id)
    # log_action(
    #     crs_action_category="scoring_submission",
    #     crs_action_name="submit_final_results",
    #     task_metadata=metadata,
    #     extra_attributes={
    #         "status": "submitting",
    #         "task_id": task_id,
    #         "task_type": "bundle",
    #         "pov_id": pov_uuid,
    #         "patch_id": patch_uuid
    #     }
    # )
    data = {
        "pov_id": pov_uuid,
        "patch_id": patch_uuid
    }
    result = submit_data(base_url, "bundle", task_id, json.dumps(data))
    # no need to confirm bundle submission
    async with lock:
        await bundle_queue.remove(task)
    # log_action(
    #     crs_action_category="scoring_submission",
    #     crs_action_name="submit_final_results",
    #     task_metadata=metadata,
    #     extra_attributes={
    #         "status": "submitted",
    #         "task_id": task_id,
    #         "task_type": "bundle",
    #         "pov_id": pov_uuid,
    #         "patch_id": patch_uuid
    #     }
    # )