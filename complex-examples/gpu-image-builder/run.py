#!/usr/bin/env python

import argparse
import json
import logging
import os
import re
import shutil
from abc import ABC
from datetime import datetime, timezone, timedelta
from time import sleep

import boto3
import pwd
import sys
from infrastructure_builder.aws import cloudformation, ecr
from infrastructure_builder.aws.batch import Batch
from infrastructure_builder.aws.exceptions import BuilderError
from infrastructure_builder.execute import execute_live
from infrastructure_builder.task_registry import task, task_registry

# Environment
user_name = re.sub(r"[^a-z0-9-]", "", pwd.getpwuid(os.getuid()).pw_name.lower())
environment = os.environ.get("ENVIRONMENT_ID", f"dev-{user_name}")
version = os.environ.get("CI_COMMIT_SHA", "dev")
cloudformation_role = os.environ.get("CLOUDFORMATION_ROLE")

# Project
project_name = "llm"
billing_tags = dict(Project=project_name)
project_params = billing_tags

aws_session = boto3.Session()


class ResourceBase(ABC):
    def __init__(self, name: str, template: str):
        self.name = name
        self.template = template
        self.stack = None


class Vpc(ResourceBase):
    def setup(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, capability_iam=True)
        return self.stack

    def destroy(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name)


class VpcNatGateway(ResourceBase):
    def setup(self, subnet_zone: str, vpc_stackname: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name + subnet_zone, self.template, billing_tags,
                                               SubnetZone=subnet_zone,
                                               ParentVPCStack=vpc_stackname)
        return self.stack

    def destroy(self, subnet_zone: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name + subnet_zone)


class BatchEnvironment(ResourceBase):
    def setup(self, vpc_stackname: str, instance_types_x86: list[str], x86_ami: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, capability_iam=True,
                                               **project_params, ParentVPCStack=vpc_stackname,
                                               InstanceTypesX86=",".join(instance_types_x86),
                                               ImageIdX86=x86_ami)
        return self.stack

    def destroy(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name)


class SampleApp(ResourceBase):
    def setup(self, docker_image: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, capability_iam=True,
                                               **project_params, ApplicationName=self.name, DockerImage=docker_image,
                                               Memory=512, Vcpus=1, Gpus=1)
        return self.stack

    def destroy(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name)


class DockerRepository(ResourceBase):
    def __init__(self, name: str, template: str, repo_name: str):
        super().__init__(name, template)
        self.repo_name = repo_name
        self.uri = None

    def setup(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, **project_params,
                                               Name=self.repo_name)
        self.uri = self.stack.output['Uri']
        return self.stack

    def login(self):
        ecr_service = ecr.ElasticContainerRegistry(aws_session)
        docker_credentials = ecr_service.get_authorization_token()
        execute_live(["docker", "login",
                      "--username", docker_credentials["user"],
                      "--password-stdin",
                      docker_credentials["hostname"]],
                     inp=docker_credentials["password"])

    def destroy(self, delete_content: bool):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name, delete_content)


class App(ResourceBase):
    def build_docker_image(self, docker_tag: str, docker_base: str, files: list[str], dockerfile: str = "Dockerfile",
                           image_platform: str = "linux/amd64"):
        docker_context = f"{docker_base}/build"
        shutil.rmtree(docker_context, ignore_errors=True)
        os.mkdir(docker_context)
        for f in files:
            if f.endswith("/"):
                shutil.copytree(f, f"{docker_context}/{f}")
            else:
                shutil.copy2(f, docker_context)

        execute_live(["docker", "buildx", "build", "--platform", image_platform, "--load",
                      "-t", docker_tag,
                      "-f", f"{docker_base}/{dockerfile}",
                      docker_context])

    def push_docker_image(self, docker_tag: str):
        execute_live(["docker", "push", docker_tag])

    def run_image(self, docker_tag: str, key_vault_name: str, storage_name: str):
        execute_live(["docker", "run", "--rm", "-it",
                      "--env", f"STORAGE_ACCOUNT={storage_name}",
                      "--env", f"KEY_VAULT={key_vault_name}",
                      docker_tag])

    def setup(self, docker_image: str, vpc_stackname: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, capability_iam=True,
                                               **project_params, ApplicationName=self.name, DockerImage=docker_image,
                                               Memory=60*1024, Vcpus=4, Gpus=1, ParentVPCStack=vpc_stackname,
                                               Environment=environment)
        return self.stack

    def destroy(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name)


class ImageBuilder(ResourceBase):
    def setup(self, parent_image: str, vpc_stackname: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, capability_iam=True,
                                               **project_params, ParentImage=parent_image,
                                               ParentVPCStack=vpc_stackname)
        return self.stack

    def destroy(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name)

    def get_current_ami(self):
        ssm = aws_session.client("ssm")
        try:
            ami_parameter = ssm.get_parameter(Name="/gpu-ecs-ami")
            current_ami = ami_parameter["Parameter"]["Value"]
            return current_ami
        except ssm.exceptions.ParameterNotFound as err:
            # Custom image has not been built yet
            raise ValueError("Please execute ./run.py updateGpuAmi to create custom machine image")


# Cloud resources
vpc = Vpc(f"{project_name}-vpc", "infrastructure/vpc-3azs.yaml")
vpc_nat_gateway = VpcNatGateway(f"{project_name}-vpc-NatGateway", "infrastructure/vpc-nat-gateway.yaml")
batch_environment = BatchEnvironment(f"{project_name}-batch-environment", "infrastructure/batch-environment.yaml")
sample_app = SampleApp(f"{project_name}-sample-app", "infrastructure/sample-app.yaml")
app_repository = DockerRepository(f"{project_name}-DockerRepository-{environment}",
                                  "infrastructure/docker-repository.yaml",
                                  f"{project_name}-app-{environment}")
app = App(f"{project_name}-app", "infrastructure/app.yaml")
image_builder = ImageBuilder(f"{project_name}-image-builder", "infrastructure/gpu-image-builder.yaml")


@task("setupCloud", description="Set up cloud environment and install applications")
def setup_cloud():
    logging.info("Set up VPC")
    vpc.setup()
    # vpc_nat_gateway.setup("A", vpc.name)
    # To keep costs low, do install NAT gateway in one Availability Zone only
    # vpc_nat_gateway.setup("B", vpc.name)
    # vpc_nat_gateway.setup("C", vpc.name)

    logging.info("Set up Batch Environment")
    current_ami = image_builder.get_current_ami()
    batch_environment.setup(vpc.name, ["g5"], current_ami)

    logging.info("Set up Batch definitions for sample app")
    sample_app.setup("nvidia/cuda:11.0.3-base")

    logging.info("Set up application")
    app_repository.setup()
    docker_image = f"{app_repository.uri}:{version}"
    app_repository.login()
    app.build_docker_image(docker_image, "app", ["src/", "requirements.txt"], "Dockerfile", "linux/amd64")
    app.push_docker_image(docker_image)
    app.setup(docker_image, vpc.name)


@task("destroyCloud", description="Tear down cloud environment")
def destroy_cloud():
    delete_content = environment != "main"
    sample_app.destroy()
    batch_environment.destroy()
    vpc.destroy()


@task("nvidiasmi", description="Run nvidia-smi in AWS Batch")
def run_nvidiasmi_app():
    setup_cloud()

    batch_service = Batch(aws_session)
    batch_service.submit_job(f"{sample_app.name}-{environment}", batch_environment.stack.output["OnDemandX86Queue"],
                             sample_app.stack.output["Job"])


@task("app", description="Run app")
def run_sample_app():
    setup_cloud()

    batch_service = Batch(aws_session)
    batch_service.submit_job(f"{app.name}-{environment}", batch_environment.stack.output["OnDemandX86Queue"],
                             app.stack.output["Job"])


@task("download", description="Download Starcoder MML")
def run_download_app():
    hugging_face_token = os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if hugging_face_token is None:
        raise ValueError("Please provide access token for StarCoder in environment variable HUGGING_FACE_HUB_TOKEN")

    setup_cloud()

    batch_service = Batch(aws_session)
    batch_service.submit_job(f"{app.name}-download-{environment}", batch_environment.stack.output["OnDemandX86Queue"],
                             app.stack.output["DownloadJob"],
                             dict(environment=[{"name": "HUGGING_FACE_HUB_TOKEN", "value": hugging_face_token}]))


@task("finetuning", description="Finetune model")
def run_finetuning_app():
    hugging_face_token = os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if hugging_face_token is None:
        raise ValueError("Please provide access token for StarCoder in environment variable HUGGING_FACE_HUB_TOKEN")

    wandb_api_key = os.environ.get("WANDB_API_KEY")
    if wandb_api_key is None:
        raise ValueError("Please provide token for WAndB in environment variable WANDB_API_KEY")

    setup_cloud()

    batch_service = Batch(aws_session)
    batch_service.submit_job(f"{app.name}-download-{environment}", batch_environment.stack.output["OnDemandX86Queue"],
                             app.stack.output["FinetuningJob"],
                             dict(environment=[{"name": "WANDB_API_KEY", "value": wandb_api_key},
                                               {"name": "HUGGING_FACE_HUB_TOKEN", "value": hugging_face_token}]))


@task("updateGpuAmi", description="Update the GPU machine image")
def run_update_gpu_ami():
    logging.info("Set up VPC")
    vpc.setup()

    # Get default AMI to be used for GPU instances
    logging.info("Determine default AMI to be used for GPU instances")
    ssm = aws_session.client("ssm")
    gpu_parameter = ssm.get_parameter(Name="/aws/service/ecs/optimized-ami/amazon-linux-2/gpu/recommended")
    gpu_parameter_value = json.loads(gpu_parameter["Parameter"]["Value"])
    recommended_gpu_ami = gpu_parameter_value["image_id"]

    # Initiate building of custom image based on default image as determined above
    logging.info("Initiate building of custom image")
    image_builder_stack = image_builder.setup(recommended_gpu_ami, vpc.name)
    image_builder_client = aws_session.client("imagebuilder")
    image_builder_execution = image_builder_client.start_image_pipeline_execution(
        imagePipelineArn=image_builder_stack.output["ImagePipeline"]
    )

    # Wait for completion
    built_ami = None
    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=60)
    current_status = None
    while True:
        if datetime.now(timezone.utc) > end:
            raise BuilderError("Timeout")

        image = image_builder_client.get_image(imageBuildVersionArn=image_builder_execution["imageBuildVersionArn"])
        build_status = image["image"]["state"]["status"]
        if build_status != current_status:
            current_status = build_status

            message = build_status
            reason = image["image"]["state"].get("reason", None)
            if reason is not None:
                message += f" ({reason})"
            logging.info(message)

        if build_status in ["AVAILABLE"]:
            for image_ami in image["image"]["outputResources"]["amis"]:
                logging.info(f'{image_ami["region"]}: {image_ami["image"]}')
                built_ami = image_ami["image"]
            break
        if build_status in ["CANCELLED", "FAILED", "DEPRECATED", "DELETED"]:
            break

        sleep(5)

    # Store AMI of custom image in Systems Manager
    ssm.put_parameter(Name="/gpu-ecs-ami", Value=built_ami,
                      Description="Recommended GPU-ECS-optimized image with encrypted EBS, resized to 200 GB.",
                      Type="String", Overwrite=True, DataType="aws:ec2:image")
    logging.info(f"Custom image {built_ami} built, ID saved in Systems Manager parameter /gpu-ecs-ami")


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
