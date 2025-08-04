#!/usr/bin/env python

import argparse
import logging
import os
import re
import shutil
from abc import ABC
from dataclasses import dataclass

import boto3
import pwd
import sys
import zlib
from infrastructure_builder.aws import cloudformation, route53, ecr
from infrastructure_builder.execute import execute_live
from infrastructure_builder.task_registry import task, task_registry
from time import sleep

# Environment
user_name = re.sub(r"[^a-z0-9-]", "", pwd.getpwuid(os.getuid()).pw_name.lower())
environment = os.environ.get("ENVIRONMENT_ID", f"dev-{user_name}")
version = os.environ.get("CI_COMMIT_SHA", "dev")
cloudformation_role = os.environ.get("CLOUDFORMATION_ROLE")

# Project
project_name = "mautic"
billing_tags = dict(Project=project_name)
project_params = billing_tags

# Service discovery domain
# Main branch: mautic
# Other branches: slug.mautic
# Local: dev-xxx.mautic
if os.environ.get("ENVIRONMENT_ID"):
    service_prefix = "" if os.environ["ENVIRONMENT_ID"] == "main" else f"{environment}."
else:
    service_prefix = f"dev-{user_name}."
service_domain = f"{service_prefix}mautic"

# Domain
# Main branch: mautic.domain.com
# Other branches: slug.mautic.domain.com
# Local: dev-xxx.mautic.domain.com
domain_suffix = "domain.com"
if os.environ.get("ENVIRONMENT_ID"):
    subdomain = "" if os.environ["ENVIRONMENT_ID"] == "main" else f"{environment}."
else:
    subdomain = f"dev-{user_name}."
mautic_domain = f"{subdomain}mautic.{domain_suffix}"


@dataclass
class FargateResources:
    vcpus: int
    memory: int

    # Valid CPU / memory combinations
    # Source: https://docs.aws.amazon.com/AmazonECS/latest/userguide/create-task-definition.html
    # Key: CPU power
    # Value: Possible memory configurations (MBytes)
    valid_combinations = {
        256: [512, 1024, 2048],
        512: [1024, 2048, 3072, 4096],
        1024: [2048, 3072, 4096, 5120, 6144, 7168, 8192],
        2048: [4096, 5120, 6144, 7168, 8192, 9216, 10240, 11264, 12288, 13312, 14336, 15360, 16384],
        4096: [8192, 9216, 10240, 11264, 12288, 13312, 14336, 15360, 16384, 17408, 18432, 19456, 20480, 21504, 22528,
               23552, 24576, 25600, 26624, 27648, 28672, 29696, 30720]
    }

    def __post_init__(self):
        if self.vcpus not in self.valid_combinations and self.memory not in self.valid_combinations[self.vcpus]:
            raise ValueError("Invalid CPU/memory combination")


mysql_resources = FargateResources(1024, 2048)
mautic_resources = FargateResources(1024, 2048)
mailpit_resources = FargateResources(512, 1024)


aws_session = boto3.Session()


class ResourceBase(ABC):
    def __init__(self, name: str, template: str):
        self.name = name
        self.template = template
        self.stack = None


class ServiceDiscovery(ResourceBase):
    def setup(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags,
                                               **project_params,
                                               DnsName=service_domain,
                                               ParentVPCStack="common-vpc")
        return self.stack

    def destroy(self, delete_content: bool):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name, delete_content)


class MySql(ResourceBase):
    def setup(self, service_discovery_name: str, service_discovery_stackname: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, capability_iam=True,
                                               **project_params,
                                               Environment=environment,
                                               ParentVPCStack="common-vpc",
                                               DBRootPassword="superadmin",
                                               DBName="mautic",
                                               DBUsername="mautic",
                                               DBPassword="mauticpwd",
                                               Cpu=mysql_resources.vcpus,
                                               Memory=mysql_resources.memory,
                                               ServiceDiscoveryName=service_discovery_name,
                                               ContainerClusterAlbStack="common-ContainerClusterAlb",
                                               ServiceDiscoveryStack=service_discovery_stackname)
        return self.stack

    def destroy(self, delete_content: bool):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name, delete_content)


class Mautic(ResourceBase):
    def calc_load_balancer_rule_priority(self) -> str:
        """
        Calculates the priority by transforming the name into some number, converted to a string.
        :return: Priority
        """
        return str(zlib.adler32(self.name.encode()) % 50000)

    def setup(self, mysql_hostname: str, mysql_stack_name: str, admin_username: str, admin_password: str,
              admin_email_address: str, mail_server_hostname: str, mail_server_port: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, capability_iam=True,
                                               **project_params,
                                               Environment=environment,
                                               ParentVPCStack="common-vpc",
                                               Hostname=mautic_domain,
                                               AdminUsername=admin_username,
                                               AdminPassword=admin_password,
                                               AdminEmailAddress=admin_email_address,
                                               DBHost=mysql_hostname,
                                               DBName="mautic",
                                               DBUsername="mautic",
                                               DBPassword="mauticpwd",
                                               MailServerHost=mail_server_hostname,
                                               MailServerPort=mail_server_port,
                                               Cpu=mautic_resources.vcpus,
                                               Memory=mautic_resources.memory,
                                               LoadBalancerRulePriority=self.calc_load_balancer_rule_priority(),
                                               ContainerClusterAlbStack="common-ContainerClusterAlb",
                                               MySqlStack=mysql_stack_name)
        return self.stack

    def redeploy(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.describe_stack(self.name)

        logging.info("Redeploying service")
        ecs_client = aws_session.client("ecs")
        ecs_client.update_service(cluster=self.stack.output["Cluster"],
                                  service=self.stack.output["EcsService"],
                                  forceNewDeployment=True)
        sleep(60)

        logging.info("Waiting until redeployment has finished...")
        while True:
            sleep(5)

            # Wait until service has one task only
            service_status = ecs_client.describe_services(cluster=self.stack.output["Cluster"],
                                                          services=[self.stack.output["EcsService"]])
            if service_status["services"][0]["runningCount"] + service_status["services"][0]["pendingCount"] == 1:
                break

        logging.info("Redeployment finished.")

    def destroy(self, delete_content: bool):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name, delete_content)


class Subdomain(ResourceBase):
    def setup(self, domain: str):
        # Query configured hosted zones
        route53_service = route53.Route53(aws_session)
        hosted_zones = {hosted_zone["Name"][:-1]: hosted_zone["Id"].removeprefix("/hostedzone/")
                        for hosted_zone in route53_service.list_hosted_zones()}

        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, True, **project_params,
                                               Domain=domain,
                                               Route53HostedZone=hosted_zones[domain_suffix],
                                               ContainerClusterAlbStack="common-ContainerClusterAlb")
        return self.stack

    def destroy(self, delete_content: bool):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name, delete_content)


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

    def build_docker_image(self, docker_tag: str, docker_base: str, files: list[str], dockerfile: str = "Dockerfile",
                           platform: str = "linux/arm64/v8"):
        docker_context = f"{docker_base}/build"
        shutil.rmtree(docker_context, ignore_errors=True)
        os.mkdir(docker_context)
        for f in files:
            if f.endswith("/"):
                shutil.copytree(f"{docker_base}/{f}", f"{docker_context}/{f}")
            else:
                shutil.copy2(f"{docker_base}/{f}", docker_context)

        execute_live(["docker", "buildx", "build", "--platform", platform, "--pull", "--load",
                      "-t", docker_tag,
                      "-f", f"{docker_base}/{dockerfile}",
                      docker_context])

    def push_docker_image(self, docker_tag: str):
        execute_live(["docker", "push", docker_tag])

    def destroy(self, delete_content: bool):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name, delete_content)


class Mailpit(ResourceBase):
    def calc_load_balancer_rule_priority(self) -> str:
        """
        Calculates the priority by transforming the name into some number, converted to a string.
        :return: Priority
        """
        return str(zlib.adler32(self.name.encode()) % 50000)

    def setup(self, hostname: str, docker_image: str, service_discovery_name: str, service_discovery_stackname: str):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.create_or_update_stack(self.name, self.template, billing_tags, capability_iam=True,
                                               **project_params,
                                               Environment=environment,
                                               Hostname=hostname,
                                               DockerImage=docker_image,
                                               ParentVPCStack="common-vpc",
                                               Cpu=mailpit_resources.vcpus,
                                               Memory=mailpit_resources.memory,
                                               ServiceDiscoveryName=service_discovery_name,
                                               ContainerClusterAlbStack="common-ContainerClusterAlb",
                                               LoadBalancerRulePriority=self.calc_load_balancer_rule_priority(),
                                               ServiceDiscoveryStack=service_discovery_stackname)
        return self.stack

    def redeploy(self):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        self.stack = cf.describe_stack(self.name)

        logging.info("Redeploying service")
        ecs_client = aws_session.client("ecs")
        ecs_client.update_service(cluster=self.stack.output["Cluster"],
                                  service=self.stack.output["EcsService"],
                                  forceNewDeployment=True)
        sleep(60)

        logging.info("Waiting until redeployment has finished...")
        while True:
            sleep(5)

            # Wait until service has one task only
            service_status = ecs_client.describe_services(cluster=self.stack.output["Cluster"],
                                                          services=[self.stack.output["EcsService"]])
            if service_status["services"][0]["runningCount"] + service_status["services"][0]["pendingCount"] == 1:
                break

        logging.info("Redeployment finished.")

    def destroy(self, delete_content: bool):
        cf = cloudformation.CloudFormation(aws_session, role_arn=cloudformation_role)
        cf.delete_stack(self.name, delete_content)


# Cloud resources
service_discovery = ServiceDiscovery(f"{project_name}-ServiceDiscovery-{environment}",
                                     "infrastructure/service-discovery.yaml")
mysql = MySql(f"{project_name}-MySQL-{environment}",
              "infrastructure/mysql.yaml")
mautic = Mautic(f"{project_name}-Mautic-{environment}",
                "infrastructure/mautic.yaml")
mautic_subdomain = Subdomain(f"{project_name}-MauticSubdomain-{environment}",
                             "infrastructure/subdomain.yaml")
mailpit_docker_repository = DockerRepository(f"{project_name}-DockerRepositoryMailpit-{environment}",
                                             "infrastructure/docker-repository.yaml",
                                             f"{project_name}-mailpit-{environment}")
mailpit_subdomain = Subdomain(f"{project_name}-MailpitSubdomain-{environment}",
                              "infrastructure/subdomain.yaml")
mailpit = Mailpit(f"{project_name}-Mailpit-{environment}",
                  "infrastructure/mailpit.yaml")


@task("setupCloud", description="Set up cloud environment and install applications")
def setup_cloud():
    logging.info("Set up service discovery")
    service_discovery_stack = service_discovery.setup()

    logging.info("Set up database")
    mysql.setup("mysqldb", service_discovery_stack.name)

    logging.info("Build Mailpit")
    mailpit_docker_repository.setup()
    docker_image = f"{mailpit_docker_repository.uri}:{version}"
    mailpit_docker_repository.login()
    mailpit_docker_repository.build_docker_image(docker_image, "mailpit", ["basic_auth.txt"], "Dockerfile")
    mailpit_docker_repository.push_docker_image(docker_image)

    logging.info("Set up Mailpit")
    mailpit_domain = f"mailpit.{mautic_domain}"
    mailpit_subdomain.setup(mailpit_domain)
    mailpit.setup(mailpit_domain, docker_image, "mailpit", service_discovery_stack.name)

    logging.info("Set up Mautic")
    mautic_subdomain.setup(mautic_domain)
    mautic.setup(f"mysqldb.{service_domain}", mysql.name, "administrator", "SomeSecretPassword",
                 "please.change.me@email.address", f"mailpit.{service_domain}", "1025")

    logging.info(f"Mautic: https://{mautic_domain}/")
    logging.info(f"  Initial Credentials: administrator / SomeSecretPassword")
    logging.info(f"Mailpit: https://{mailpit_domain}/")
    logging.info(f"  Basic auth: administrator / SomeSecretPassword")


@task("redeployMautic", description="Redeploy Mautic after update (needed when Docker image tag does not change)")
def redeploy_opencart():
    mautic.redeploy()


@task("redeployMailpit", description="Redeploy Mailpit after update (needed when Docker image tag does not change)")
def redeploy_opencart():
    mailpit.redeploy()


@task("destroyCloud", description="Tear down cloud environment")
def destroy_cloud():
    delete_content = environment != "main"
    mautic.destroy(delete_content)
    mautic_subdomain.destroy(delete_content)
    mailpit.destroy(delete_content)
    mailpit_subdomain.destroy(delete_content)
    mailpit_docker_repository.destroy(delete_content)
    mysql.destroy(delete_content)
    service_discovery.destroy(delete_content)


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
