import shlex
import sys
import subprocess
import logging
import os

def _get_command_string(command):
  """Returns a shell escaped command string."""
  return ' '.join(shlex.quote(part) for part in command)

def _env_to_docker_args(env_list):
  """Turns envirnoment variable list into docker arguments."""
  return sum([['-e', v] for v in env_list], [])

def docker_run(run_args, print_output=True, architecture='x86_64'):
  """Calls `docker run`."""
  platform = 'linux/arm64' if architecture == 'aarch64' else 'linux/amd64'
  command = [
      'docker', 'run', '--privileged', '--shm-size=2g', '--platform', platform
  ]
  if os.getenv('OSS_FUZZ_SAVE_CONTAINERS_NAME'):
    command.append('--name')
    command.append(os.getenv('OSS_FUZZ_SAVE_CONTAINERS_NAME'))
  else:
    command.append('--rm')

  # Support environments with a TTY.
  if sys.stdin.isatty():
    command.append('-i')

  command.extend(run_args)

  logging.info('Running: %s.', _get_command_string(command))
  stdout = None
  if not print_output:
    stdout = open(os.devnull, 'w')

  try:
    subprocess.check_call(command, stdout=stdout, stderr=subprocess.STDOUT)
  except subprocess.CalledProcessError:
    return False

  return True