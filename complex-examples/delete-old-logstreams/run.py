#!/usr/bin/env python

import argparse
import logging
import os
import re
from abc import ABC

import boto3
import pwd
import sys
from infrastructure_builder.aws import cloudformation
from infrastructure_builder.task_registry import task, task_registry

# Environment
user_name = re.sub(r"[^a-z0-9-]", "", pwd.getpwuid(os.getuid()).pw_name.lower())
environment = os.environ.get("ENVIRONMENT_ID", f"dev-{user_name}")
version = os.environ.get("CI_COMMIT_SHA", "dev")
cloudformation_role = os.environ.get("CLOUDFORMATION_ROLE")

# Project
project_name = "aws-maintenance"
billing_tags = dict(Project=project_name)
project_params = billing_tags


aws_session = boto3.Session()


class ResourceBase(ABC):
    def __init__(self, name: str, template: str):
        self.name = name
        self.template = template
        self.stack = None


class LambdaFunction(ResourceBase):
    def setup(self, source_code_filename: str, handler: str, runtime: str):
        with open(source_code_filename, "r") as reader:
            source_code = reader.read()

        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, True, **project_params,
                                               SourceCode=source_code,
                                               Handler=handler,
                                               Runtime=runtime,
                                               MemorySize="128",
                                               Timeout="900",  # 15 minutes
                                               ScheduleCron="cron(13 3 * * ? *)",
                                               ScheduleState="ENABLED")
        return self.stack

    def destroy(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name, True)


# Cloud resources
delete_old_logstreams_function = LambdaFunction(f"{project_name}-DeleteOldLogstreams-{environment}",
                                                "infrastructure/delete_old_logstreams.yaml")


@task("setupCloud", description="Set up cloud environment and install applications")
def setup_cloud():
    logging.info("Set up Lambda functions")
    delete_old_logstreams_function.setup("delete_old_logstreams.py", "index.lambda_handler", "python3.10")


@task("destroyCloud", description="Tear down cloud environment")
def destroy_cloud():
    delete_old_logstreams_function.destroy()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    valid_tasks = f"Valid tasks:\n{task_registry.format_task_descriptions()}"
    parser = argparse.ArgumentParser(description="Build, run and deploy", epilog=valid_tasks,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("tasks", metavar="task", type=str, nargs='+',
                        help="Task to execute")
    args = parser.parse_args(None if sys.argv[1:] else ["-h"])  # print help if no task was given

    for t in args.tasks:
        task_to_execute = task_registry.get_task(t)
        if task_to_execute is None:
            logging.error(f"Unknown task {t}")
            logging.error(valid_tasks)
            return

        task_to_execute.execute()


if __name__ == "__main__":
    main()
