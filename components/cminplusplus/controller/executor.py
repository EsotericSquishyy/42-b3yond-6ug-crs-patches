import asyncio
import logging

async def run_command(cmd, cwd = None, errorable = False, timeout = None) -> bytes:
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=False,
        )
        if timeout:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        else:
            stdout, stderr = await process.communicate()
    except asyncio.TimeoutError:
        logging.error(f"Command timed out: {cmd}")
        process.kill()
        # await process.wait()
        logging.error(f"Process killed: {cmd}")
        return b"Timeout", b"Timeout"

    if errorable:
        return stdout, stderr
    else:
        if process.returncode != 0:
            # print(stderr)
            raise RuntimeError(f"Command failed")

        return stdout, stderr