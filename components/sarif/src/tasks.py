import threading
import logging
import subprocess
import os
import json

from sariffile import parse_sarif_report

from checkers.slice import SliceChecker
from checkers.directed_fuzzing import DirectedFuzzingChecker
from checkers.seeds import SeedsChecker

from db import DBConnection

from models.sarif_results import SarifResults

from utils.thread import ExceptionThread

from ossfuzz import is_jvm_project

from utils.common import gen_dict_extract

class SarifTaskWorker:
    def __init__(self, task_id, sarif_id, id, project_dir, diff_file, sarif_file, original_msg = None, workspace_dir = None):
        # task id is challenge id here
        self.task_id = task_id
        self.sarif_id = sarif_id
        self.id = id
        self.project_dir = project_dir
        self.diff_file = diff_file
        self.sarif_file = sarif_file
        self.workspace_dir = workspace_dir
        self.thread = ExceptionThread(target=self._run)
        self.stop_event = threading.Event()
        self.original_msg = original_msg
        self.thread.start()
        
    def _run(self):
        # start the worker
        logging.info('Started worker %s', self.id)
        logging.info('Worker %s | Project %s', self.id, self.project_dir)
        logging.info('Worker %s | Diff %s', self.id, self.diff_file)
        logging.info('Worker %s | Sarif %s', self.id, self.sarif_file)

        # parse sarif reports 
        results, stats = parse_sarif_report(self.project_dir, self.sarif_file)
        # output stats info
        logging.info('Worker %s | Stats %s', self.id, stats)
        # logging.debug('Worker %s | Results %s', self.id, results)
        self.sarif_results = results
        self.sarif_stats = stats
        logging.debug('Worker %s | Sarif results %s', self.id, self.sarif_results)
        # call assess_sarif_report()
        ret, desc = self.assess_sarif_report()

        # send the report to CRS, using db
        db_connection = DBConnection(db_url = os.getenv('DATABASE_URL'))

        if ret == True:
            logging.info('Worker %s | Report: Correct SARIF', self.id)
            try:
                db_connection.write_to_db(SarifResults(sarif_id = self.sarif_id, result = True, task_id = self.task_id, description = desc))
                logging.debug('Worker %s | Wrote to db', self.id)
            except Exception as e:
                logging.error('Worker %s | Failed to write to db: %s', self.id, e)
                raise e
        elif ret == False:
            logging.info('Worker %s | Report: Incorrect SARIF', self.id)
            try:
                db_connection.write_to_db(SarifResults(sarif_id = self.sarif_id, result = False, task_id = self.task_id, description = desc))
                logging.debug('Worker %s | Wrote to db', self.id)
            except Exception as e:
                logging.error('Worker %s | Failed to write to db: %s', self.id, e)
                raise e
        elif ret == None:
            logging.info('Worker %s | Report: Prefer not to report', self.id)

    def assess_sarif_report(self):

        # experimental: deal with the case when the SARIF report contains files that are not in the codebase
        # this happens in official example SARIF reports

        if self.sarif_stats['no_file'] > 0:
            logging.warning('Worker %s | SARIF report contains %d files that are not in the codebase', self.id, self.sarif_stats['no_file'])
            return False, "File name error"
        
        # TODO: process JAVA
        if is_jvm_project(os.path.join(self.workspace_dir, "fuzz-tooling"), self.original_msg['project_name']):
            logging.warning('Worker %s | This is a JAVA sarif, currently we just use AI', self.id)
            # Invoke AI 
            # try 3 times:
            result = None
            for i in range(20):
                if os.path.exists(os.path.join(self.workspace_dir, 'result.json')):
                    os.remove(os.path.join(self.workspace_dir, 'result.json'))
                try:
                    result = subprocess.check_call([
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
                    ], cwd = os.path.join(os.getenv('AGENT_ROOT', '/app'), 'crs-prime-sarif-evaluator'))

                    # extract the result
                    if not os.path.exists(os.path.join(self.workspace_dir, 'result.json')):
                        logging.error('Worker %s | Failed to run AI: %s', self.id, 'result.json not found')
                        continue
                    
                    json_result = json.load(open(os.path.join(self.workspace_dir, 'result.json'), 'r'))

                    if 'assessment' not in json_result:
                        logging.warning('Worker %s | Non-standard AI result: %s', self.id, json_result)
                        assessment = 'incorrect'
                        for a in gen_dict_extract('assessment', json_result):
                            if a == 'correct':
                                assessment = a
                                break
                    else:
                        assessment = json_result['assessment']

                    # check the result  
                    if assessment == 'correct':
                        logging.info('Worker %s | AI result: Correct SARIF', self.id)
                        return True, json_result['description'] if 'description' in json_result else 'Correct SARIF'
                    elif assessment == 'incorrect':
                        logging.info('Worker %s | AI result: Incorrect SARIF', self.id)
                        return False, json_result['description'] if 'description' in json_result else 'Incorrect SARIF'
                    else:
                        logging.warning('Worker %s | AI result: Prefer not to report', self.id)
                        return None, json_result['description'] if 'description' in json_result else 'Prefer not to report'
                except Exception as e:
                    logging.error('Worker %s | Failed to run AI: %s', self.id, e)
                    continue
            
            # if we reach here, it means we failed to run AI
            logging.error('Worker %s | Failed to run AI after 3 attempts', self.id)
            return None, 'Prefer not to report'
                
        
        # start slice checker
        # slice_checker = SliceChecker(self.task_id, self.sarif_id, self.sarif_results, original_msg = self.original_msg, project_dir = self.project_dir)
        # slice_checker.stop()
        # if slice_checker.result == False:
        #    return False, "Target not reachable"
        # slice_path = slice_checker.slice_path
        # start directed fuzzing checker
        # df_checker = DirectedFuzzingChecker(self.task_id, self.sarif_id, self.sarif_results, original_msg = self.original_msg, slice_path = slice_path)
        # it just sent a message to the queue, just let it run
        #df_checker.stop()
        # start seeds checker
        seeds_checker = SeedsChecker(self.task_id, self.sarif_results, original_msg = self.original_msg, fuzzing_tooling=self.original_msg['fuzzing_tooling'], project_dir = self.project_dir, sarif_file = self.sarif_file, workspace_dir = self.workspace_dir)
        seeds_checker.stop()
        return seeds_checker.result, seeds_checker.description

    def stop(self, kill = False):
        if kill:
            self.stop_event.set()
            self.thread.join()
            logging.warning('Killed worker %s', self.id)
        else:
            self.thread.join()
            logging.info('Stopped worker %s', self.id) 



