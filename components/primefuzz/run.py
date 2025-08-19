#!/usr/bin/env python3
import asyncio
from modules.config import Config
from workflow import FuzzingWorkflow


async def main():
    print("Starting the basic fuzzing workflow and waiting for tasks...")
    config = Config.from_env()
    async with FuzzingWorkflow(config) as workflow:
        await workflow.start()

    # Wait for all tasks to finish
    tasks = [t for t in asyncio.all_tasks(
    ) if t is not asyncio.current_task()]
    # cancel all tasks
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
