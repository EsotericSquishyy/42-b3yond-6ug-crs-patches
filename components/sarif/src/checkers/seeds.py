import threading
import logging
import os
import time
import subprocess
import shutil
import re
import uuid
import json

from sqlalchemy import select

from utils.thread import ExceptionThread

from ossfuzz import OSSFuzzRunner

from db import DBConnection

from models.bugs import Bugs
from models.bug_groups import BugGroups
from models.bug_profiles import BugProfiles
from models.tasks import Task, TaskStatusEnum
from utils.common import gen_dict_extract
class SeedsChecker:
    def __init__(self, task_id, sarif_results, fuzzing_tooling, original_msg, project_dir, sarif_file, workspace_dir = None):
        self.task_id = task_id
        self.sarif_results = sarif_results
        self.fuzzing_tooling = fuzzing_tooling
        self.workspace_dir = workspace_dir
        self.thread = ExceptionThread(target=self._run)
        self.original_msg = original_msg
        self.stop_event = threading.Event()
        self.result = None
        self.project_dir = project_dir
        self.sarif_file = sarif_file
        self.description = ""
        self.thread.start()
        

    def _run(self):
        # start the worker
        logging.info('Started SeedsChecker %s', self.task_id)
        # build the oss-fuzz-tooling and fuzzer

        # fuzzing_tooling_dir = os.path.join(self.workspace_dir, 'fuzz-tooling')
        # repo_dir = os.path.join(self.workspace_dir, self.original_msg['focus'])
        # logging.info('Starting OSS Fuzz runner')
        # runner = OSSFuzzRunner(fuzzing_tooling_dir, self.original_msg['project_name'], repo_dir, self.workspace_dir)

        # inject the custom stubs 
        # prepare env
        # logging.info('Injecting custom stubs')
        # code_injector = os.path.join(os.getenv('AGENT_ROOT', '/app'), 'code_injector/build/code_injector')
        # code_injector_workdir = os.path.join(self.workspace_dir, 'code_injector_tmp')
        # if not os.path.exists(code_injector_workdir):
        #     os.mkdir(code_injector_workdir)
        # # prepare injection map
        # injection_map = {}

        # do injection
        # current_id = 0
        # successful_count = 0
        # all_target_injected = False
        # for result in self.sarif_results:
        #     target_file_path_rel = result['file']
        #     target_line_number = result['line']
        #     target_file_path = os.path.join(self.workspace_dir, self.original_msg['focus'], target_file_path_rel)
        #     # inject the custom stubs
        #     logging.debug('Injecting custom stubs to %s:%s', target_file_path, target_line_number)
        #     injected_code_path = os.path.join(code_injector_workdir, f'{current_id}.c')

        #     # find the correct target line 
        #     # TODO: this is a temporary solution, we need to find a better way to handle this
        #     if target_file_path_rel in injection_map:
        #         for injected_line in injection_map[target_file_path_rel]:
        #             if injected_line < target_line_number:
        #                 target_line_number += 1
            
        #     # invoke the code_injector
        #     r = subprocess.run([
        #         code_injector,
        #         target_file_path,
        #         '--line',
        #         str(target_line_number),
        #         '--target',
        #         str(current_id),
        #         '--outfile',
        #         injected_code_path
        #     ])

        #     # check the result
        #     if os.path.exists(injected_code_path):
        #         # copy file 
        #         os.remove(target_file_path)
        #         shutil.copy2(injected_code_path, target_file_path)
        #         # update the injection map
        #         if target_file_path_rel not in injection_map:
        #             injection_map[target_file_path_rel] = []
        #         injection_map[target_file_path_rel].append(target_line_number)
                
        #         # check if the injection was successful
        #         with open(target_file_path, 'r') as f:
        #             content = f.read()
        #             if f'AIXCC_REACH_TARGET_{current_id}' not in content:
        #                 logging.error('Injection failed for %s:%s, id %d', target_file_path, target_line_number, current_id)
        #             else:
        #                 logging.info('Injection successful for %s:%s, id %d', target_file_path, target_line_number, current_id)
        #                 successful_count += 1
        #     # print(result)
        #     current_id += 1
            
        # if successful_count == current_id:
        #     logging.info('All injections successful')
        #     all_target_injected = True   
        # target_number = 1 if successful_count == 0 else successful_count
        
        # build the fuzzer 
        # logging.info('Building fuzzer')
        # # Currently we pull the images
        # fuzz_targets = runner.build_fuzzers(is_pull = True)
        # logging.info('Fuzzer built')
        
        # Invoke AI for first round check - Check if it is "very" likely to be a false positive
        cmd = [
            'python3',
            '-m',
            'evaluator.main',
            '--model',
            'openai' if os.getenv('USE_OPENAI') else 'anthropic',
            self.sarif_file,
            self.project_dir,
            '--result_path',
            os.path.join(self.workspace_dir, 'result.json'),
            '--workspace',
            self.workspace_dir,
            '--preliminary'
        ]
        for i in range(20):
            if os.path.exists(os.path.join(self.workspace_dir, 'result.json')):
                os.remove(os.path.join(self.workspace_dir, 'result.json'))
            try:
                assessment = None
                result = subprocess.check_call(cmd, cwd = os.path.join(os.getenv('AGENT_ROOT', '/app'), 'crs-prime-sarif-evaluator'))
                json_result = json.load(open(os.path.join(self.workspace_dir, 'result.json'), 'r'))
                if 'assessment' not in json_result:
                    raise Exception('AI generated a non-standard result')
                assessment = json_result['assessment']
                break
            except Exception as e:
                logging.error('Task %s | Failed to run AI for preliminary check: %s, attempt %d', self.task_id, e, i)
                continue
        if assessment == 'incorrect':
            logging.info('Task %s | AI result: Incorrect SARIF', self.task_id)
            self.result = False
            if 'description' in json_result:
                self.description = json_result['description']
            else:
                self.description = 'Incorrect SARIF'
            self.stop_event.set()
            return
        elif assessment == 'correct':
            logging.info('Task %s | AI result: Correct SARIF', self.task_id)
            self.result = True
            if 'description' in json_result:
                self.description = json_result['description']
            else:
                self.description = 'Correct SARIF'
            self.stop_event.set()
            return
        
        logging.info('Task %s | AI did not think it is a false positive', self.task_id)    
        
        logging.info('Starting DB session')
        db_connection = DBConnection(db_url = os.getenv('DATABASE_URL'))
        db_connection.start_session()

        evaluated_crashes = set()

        # main loop: grab the seeds from the db and run the reproducers
        while not self.stop_event.is_set():
            # get current time
            current_time = time.time()
            # # TODO: grab the seeds from db
            
            # # db schema: 
            # # - bug_groups (id, bug_id, bug_profile_id)
            # # - bugs       (id, task_id, created_at, arch, poc, harness, sanitizer, sarif)

            # # what we have: task_id
            # # what we need: poc, harness, sanitizer, and get 1 bug from each bug_group

            # stmt = (
            #     select(
            #         Bugs,
            #         BugGroups.bug_profile_id
            #     )
            #     .join(BugGroups, Bugs.id == BugGroups.bug_id)
            #     .where(Bugs.task_id == self.task_id)
            #     .distinct(BugGroups.bug_profile_id)
            # )
            
            # get task deadline
            stmt = (
                select(
                    Task.status
                ).where(
                    Task.id == self.task_id
                )
            )
            task_status = db_connection.execute_stmt_with_session(stmt)[0]
            if task_status != TaskStatusEnum.processing:
                logging.info('Task %s | Task not processing', self.task_id)
                self.stop_event.set()
                self.result = None
                self.description = 'Task not processing'
                break
            
            stmt = (
                select(
                    BugProfiles,
                ).where(
                    BugProfiles.task_id == self.task_id
                )
            )

            bug_profiles = db_connection.execute_stmt_with_session(stmt)
            crashes = [(bug_profiles.id, bug_profiles.summary) for bug_profiles in bug_profiles]
            logging.info('Task %s | Got %d crashes from db', self.task_id, len(crashes))
            logging.debug('Task %s | Crashes %s', self.task_id, crashes)
            # run the reproducers
            for crash in crashes:
                if self.stop_event.is_set():
                    break
                self.result = None
                if crash[0] in evaluated_crashes:
                    logging.info('Task %s | Crash %s already evaluated', self.task_id, crash[0])
                    continue
                # copy the poc to another location to avoid naming issues
                # new_poc_path = os.path.join(self.workspace_dir, uuid.uuid4().hex)
                # shutil.copy2(seed[0], new_poc_path)
                # # run
                # logging.info('Task %s | Running reproducers for seed %s', self.task_id, seed[0])
                # result_stdout, result_stderr = runner.reproduce(new_poc_path, seed[1])
                # logging.debug('Task %s | Result stdout: %s', self.task_id, result_stdout)
                # logging.debug('Task %s | Result stderr: %s', self.task_id, result_stderr)
                # # check if the result crashes == contains 'Sanitizer'?
                # # TODO: a smarter way to detect crash
                # # if 'Sanitizer' in result_stderr:
                #     # detect all the `AIXCC_REACH_TARGET_` in the result
                # reached_targets = re.findall(rb'AIXCC_REACH_TARGET_[0-9]+', result_stdout)
                # # deduplicate the targets
                # reached_targets = list(set(reached_targets))
                # logging.info('Task %s | Reached targets %s', self.task_id, reached_targets)
                # # confirm that all the targets are reached
                # if len(reached_targets) == target_number:
                #     # <crash & reached targets> -> return true?
                #     logging.info('Task %s | All targets reached', self.task_id)
                #     self.result = True
                #     # self.stop_event.set()
                #     # break
                # else:
                #     # <crash & not reached targets> -> return false?
                #     logging.error('Task %s | Not all targets reached', self.task_id)
                #     self.result = False
                    # self.stop_event.set()
                # extract the crash report and save it to workspace
                crash_report_path = os.path.join(self.workspace_dir, 'crash_report')
                if os.path.exists(crash_report_path):
                    os.remove(crash_report_path)
                # truncate the crash report from the stdout
                # if b'===================================' in result_stdout:
                #     report_content = result_stdout.split(b'===================================')[1]
                # else:
                #     logging.error('Task %s | Crash report not found in stdout', self.task_id)
                #     continue
                with open(crash_report_path, 'wb') as f:
                    f.write(crash[1].encode('utf-8'))
                
                cmd = [
                    'python3',
                    '-m',
                    'evaluator.main',
                    '--model',
                    'openai' if os.getenv('USE_OPENAI') else 'anthropic',
                    self.sarif_file,
                    self.project_dir,
                    '--result_path',
                    os.path.join(self.workspace_dir, 'result.json'),
                    '--crash_path',
                    crash_report_path,
                    '--workspace',
                    self.workspace_dir,
                ]
                # if self.result == True and all_target_injected:
                #     cmd.append('--is_reached')
                for i in range(5):
                    if os.path.exists(os.path.join(self.workspace_dir, 'result.json')):
                        os.remove(os.path.join(self.workspace_dir, 'result.json'))
                    
                    # invoke AI
                    try:
                        assessment = None
                        result = subprocess.check_call(cmd, cwd = os.path.join(os.getenv('AGENT_ROOT', '/app'), 'crs-prime-sarif-evaluator'))
                        # check the result
                        json_result = json.load(open(os.path.join(self.workspace_dir, 'result.json'), 'r'))
                        if 'assessment' not in json_result:
                            # AI generated a non-standard result
                            # try to find the assessment
                            # traverse all the keys
                            assessment = 'incorrect'
                            for a in gen_dict_extract('assessment', json_result):
                                if a == 'correct':
                                    assessment = 'correct'
                        else:
                            assessment = json_result['assessment']
                        break

                    except Exception as e:
                        logging.error('Task %s | Failed to run AI: %s', self.task_id, e)
                        continue

                    
                # if assessment == 'correct':
                #     if self.result == True:
                #         logging.info('Task %s | AI result: Correct SARIF', self.task_id)
                #         self.result = True
                #         if 'description' in json_result:
                #             self.description = json_result['description']
                #         else:
                #             self.description = 'Correct SARIF'
                #         self.stop_event.set()
                #         break
                #     else:
                #         # pre-check false, AI true
                #         logging.warning('Task %s | AI result: Correct SARIF, but pre-check failed', self.task_id)
                #         break
                # elif assessment == 'incorrect':
                #     logging.info('Task %s | AI result: Incorrect SARIF', self.task_id)
                #     if self.result == True:
                #         logging.warning('Task %s | AI result: Incorrect SARIF, but pre-check passed', self.task_id)
                #         break
                #     else:
                #         logging.info('Task %s | AI result: Incorrect SARIF', self.task_id)
                #         self.result = False
                #         if 'description' in json_result:
                #             self.description = json_result['description']
                #         else:
                #             self.description = 'Incorrect SARIF'
                #         # self.stop_event.set()
                #         break
                #     break
                
                if assessment == 'correct':
                    logging.info('Task %s | AI result: Correct SARIF', self.task_id)
                    self.result = True
                    if 'description' in json_result:
                        self.description = json_result['description']
                    else:
                        self.description = 'Correct SARIF'
                    self.stop_event.set()
                    break
                
                    
                evaluated_crashes.add(crash[0])
            
            if self.stop_event.is_set():
                break
                
            
            # get elapsed time
            elapsed_time = time.time() - current_time
            # sleep for the remaining time
            if elapsed_time < 120:
                time.sleep(120 - elapsed_time)

        db_connection.stop_session()
        logging.info('Stopped SeedsChecker %s', self.task_id)



    def stop(self, kill = False):
        if kill:
            self.stop_event.set()
            self.thread.join()
            logging.warning('Killed SeedsChecker %s', self.task_id)
        else:
            self.thread.join()
            logging.info('Stopped SeedsChecker %s', self.task_id)


