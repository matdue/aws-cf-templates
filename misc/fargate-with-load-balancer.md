# AWS Fargate mit Load Balancer

Route53 record set

```json
        {
            "Name": "hello-world.domain.com.",
            "Type": "A",
            "AliasTarget": {
                "HostedZoneId": "Z215JYRZR1TBD5",
                "DNSName": "dualstack.fargate-hello-world-870046895.eu-central-1.elb.amazonaws.com.",
                "EvaluateTargetHealth": true
            }
        }
```

Load Balancer

```json
 {
            "LoadBalancerArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:loadbalancer/app/fargate-hello-world/23797fda18ac2b74",
            "DNSName": "fargate-hello-world-870046895.eu-central-1.elb.amazonaws.com",
            "CanonicalHostedZoneId": "Z215JYRZR1TBD5",
            "CreatedTime": "2020-05-27T08:37:08.360Z",
            "LoadBalancerName": "fargate-hello-world",
            "Scheme": "internet-facing",
            "VpcId": "vpc-06296a2d8e5fe7691",
            "State": {
                "Code": "active"
            },
            "Type": "application",
            "AvailabilityZones": [
                {
                    "ZoneName": "eu-central-1b",
                    "SubnetId": "subnet-0a01a1bafc5a43d07",
                    "LoadBalancerAddresses": []
                },
                {
                    "ZoneName": "eu-central-1a",
                    "SubnetId": "subnet-0cbb958b213ee2f25",
                    "LoadBalancerAddresses": []
                }
            ],
            "SecurityGroups": [
                "sg-01d742710e8b622da"
            ],
            "IpAddressType": "ipv4"
        }
```

Security Group must allow traffic from outside:

```json
 {
            "Description": "load-balancer-wizard-1 created on 2020-05-27T10:35:56.301+02:00",
            "GroupName": "fargate-hello-world",
            "IpPermissions": [
                {
                    "FromPort": 80,
                    "IpProtocol": "tcp",
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0"
                        }
                    ],
                    "Ipv6Ranges": [
                        {
                            "CidrIpv6": "::/0"
                        }
                    ],
                    "PrefixListIds": [],
                    "ToPort": 80,
                    "UserIdGroupPairs": []
                },
                {
                    "FromPort": 443,
                    "IpProtocol": "tcp",
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0"
                        }
                    ],
                    "Ipv6Ranges": [
                        {
                            "CidrIpv6": "::/0"
                        }
                    ],
                    "PrefixListIds": [],
                    "ToPort": 443,
                    "UserIdGroupPairs": []
                }
            ],
            "OwnerId": "493314881487",
            "GroupId": "sg-01d742710e8b622da",
            "IpPermissionsEgress": [
                {
                    "IpProtocol": "-1",
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0"
                        }
                    ],
                    "Ipv6Ranges": [],
                    "PrefixListIds": [],
                    "UserIdGroupPairs": []
                }
            ],
            "VpcId": "vpc-06296a2d8e5fe7691"
        }
```

Target group:

```json
 {
            "TargetGroupArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:targetgroup/ecs-fargat-hello-world/0c505c5c320f4234",
            "TargetGroupName": "ecs-fargat-hello-world",
            "Protocol": "HTTP",
            "Port": 80,
            "VpcId": "vpc-06296a2d8e5fe7691",
            "HealthCheckProtocol": "HTTP",
            "HealthCheckPort": "traffic-port",
            "HealthCheckEnabled": true,
            "HealthCheckIntervalSeconds": 30,
            "HealthCheckTimeoutSeconds": 5,
            "HealthyThresholdCount": 5,
            "UnhealthyThresholdCount": 2,
            "HealthCheckPath": "/",
            "Matcher": {
                "HttpCode": "200"
            },
            "LoadBalancerArns": [
                "arn:aws:elasticloadbalancing:eu-central-1:493314881487:loadbalancer/app/fargate-hello-world/23797fda18ac2b74"
            ],
            "TargetType": "ip"
        }

```

Listener, one for port 80 and one for port 443, with same target:

```json
{
    "Listeners": [
        {
            "ListenerArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:listener/app/fargate-hello-world/23797fda18ac2b74/05b4f05288a45bcc",
            "LoadBalancerArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:loadbalancer/app/fargate-hello-world/23797fda18ac2b74",
            "Port": 443,
            "Protocol": "HTTPS",
            "Certificates": [
                {
                    "CertificateArn": "arn:aws:acm:eu-central-1:493314881487:certificate/a3cc2b78-ef0d-44be-8772-7e334f124ce8"
                }
            ],
            "SslPolicy": "ELBSecurityPolicy-2016-08",
            "DefaultActions": [
                {
                    "Type": "forward",
                    "TargetGroupArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:targetgroup/ecs-fargat-hello-world/0c505c5c320f4234",
                    "Order": 1,
                    "ForwardConfig": {
                        "TargetGroups": [
                            {
                                "TargetGroupArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:targetgroup/ecs-fargat-hello-world/0c505c5c320f4234",
                                "Weight": 1
                            }
                        ],
                        "TargetGroupStickinessConfig": {
                            "Enabled": false
                        }
                    }
                }
            ]
        },
        {
            "ListenerArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:listener/app/fargate-hello-world/23797fda18ac2b74/fd57f3cce4d69401",
            "LoadBalancerArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:loadbalancer/app/fargate-hello-world/23797fda18ac2b74",
            "Port": 80,
            "Protocol": "HTTP",
            "DefaultActions": [
                {
                    "Type": "forward",
                    "TargetGroupArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:targetgroup/ecs-fargat-hello-world/0c505c5c320f4234",
                    "ForwardConfig": {
                        "TargetGroups": [
                            {
                                "TargetGroupArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:targetgroup/ecs-fargat-hello-world/0c505c5c320f4234",
                                "Weight": 1
                            }
                        ],
                        "TargetGroupStickinessConfig": {
                            "Enabled": false
                        }
                    }
                }
            ]
        }
    ]
}
```

Fargate cluster:

```json
{
    "clusters": [
        {
            "clusterArn": "arn:aws:ecs:eu-central-1:493314881487:cluster/fargate-hello-world",
            "clusterName": "fargate-hello-world",
            "status": "ACTIVE",
            "registeredContainerInstancesCount": 0,
            "runningTasksCount": 1,
            "pendingTasksCount": 0,
            "activeServicesCount": 1,
            "statistics": [],
            "tags": [],
            "settings": [
                {
                    "name": "containerInsights",
                    "value": "disabled"
                }
            ],
            "capacityProviders": [
                "FARGATE_SPOT",
                "FARGATE"
            ],
            "defaultCapacityProviderStrategy": []
        }
    ],
    "failures": []
}
```

Task definition:

```json
{
    "taskDefinition": {
        "taskDefinitionArn": "arn:aws:ecs:eu-central-1:493314881487:task-definition/hello-world:1",
        "containerDefinitions": [
            {
                "name": "hello-world",
                "image": "rancher/hello-world",
                "cpu": 0,
                "portMappings": [
                    {
                        "containerPort": 80,
                        "hostPort": 80,
                        "protocol": "tcp"
                    }
                ],
                "essential": true,
                "environment": [],
                "mountPoints": [],
                "volumesFrom": [],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": "/ecs/hello-world",
                        "awslogs-region": "eu-central-1",
                        "awslogs-stream-prefix": "ecs"
                    }
                }
            }
        ],
        "family": "hello-world",
        "taskRoleArn": "arn:aws:iam::493314881487:role/ecsTaskExecutionRole",
        "executionRoleArn": "arn:aws:iam::493314881487:role/ecsTaskExecutionRole",
        "networkMode": "awsvpc",
        "revision": 1,
        "volumes": [],
        "status": "ACTIVE",
        "requiresAttributes": [
            {
                "name": "com.amazonaws.ecs.capability.logging-driver.awslogs"
            },
            {
                "name": "ecs.capability.execution-role-awslogs"
            },
            {
                "name": "com.amazonaws.ecs.capability.docker-remote-api.1.19"
            },
            {
                "name": "com.amazonaws.ecs.capability.task-iam-role"
            },
            {
                "name": "com.amazonaws.ecs.capability.docker-remote-api.1.18"
            },
            {
                "name": "ecs.capability.task-eni"
            }
        ],
        "placementConstraints": [],
        "compatibilities": [
            "EC2",
            "FARGATE"
        ],
        "requiresCompatibilities": [
            "FARGATE"
        ],
        "cpu": "256",
        "memory": "512"
    }
}
```

ecsTaskExecutionRole:

```json
{
    "Role": {
        "Path": "/",
        "RoleName": "ecsTaskExecutionRole",
        "RoleId": "AROAXFW63W7HTYDC5R7Q6",
        "Arn": "arn:aws:iam::493314881487:role/ecsTaskExecutionRole",
        "CreateDate": "2020-04-27T09:31:38Z",
        "AssumeRolePolicyDocument": {
            "Version": "2008-10-17",
            "Statement": [
                {
                    "Sid": "",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ecs-tasks.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        },
        "MaxSessionDuration": 3600,
        "RoleLastUsed": {
            "LastUsedDate": "2020-05-27T13:07:34Z",
            "Region": "eu-central-1"
        }
    }
}
```

Fargate service:

```json
{
    "services": [
        {
            "serviceArn": "arn:aws:ecs:eu-central-1:493314881487:service/fargate-hello-world/hello-world",
            "serviceName": "hello-world",
            "clusterArn": "arn:aws:ecs:eu-central-1:493314881487:cluster/fargate-hello-world",
            "loadBalancers": [
                {
                    "targetGroupArn": "arn:aws:elasticloadbalancing:eu-central-1:493314881487:targetgroup/ecs-fargat-hello-world/0c505c5c320f4234",
                    "containerName": "hello-world",
                    "containerPort": 80
                }
            ],
            "serviceRegistries": [],
            "status": "ACTIVE",
            "desiredCount": 1,
            "runningCount": 1,
            "pendingCount": 0,
            "launchType": "FARGATE",
            "platformVersion": "LATEST",
            "taskDefinition": "arn:aws:ecs:eu-central-1:493314881487:task-definition/hello-world:1",
            "deploymentConfiguration": {
                "maximumPercent": 200,
                "minimumHealthyPercent": 100
            },
            "deployments": [
                {
                    "id": "ecs-svc/3982166039798482380",
                    "status": "PRIMARY",
                    "taskDefinition": "arn:aws:ecs:eu-central-1:493314881487:task-definition/hello-world:1",
                    "desiredCount": 1,
                    "pendingCount": 0,
                    "runningCount": 1,
                    "createdAt": 1590569101.303,
                    "updatedAt": 1590569152.935,
                    "launchType": "FARGATE",
                    "platformVersion": "1.3.0",
                    "networkConfiguration": {
                        "awsvpcConfiguration": {
                            "subnets": [
                                "subnet-0cbb958b213ee2f25",
                                "subnet-0a01a1bafc5a43d07"
                            ],
                            "securityGroups": [
                                "sg-0de8dc0f9116af675"
                            ],
                            "assignPublicIp": "ENABLED"
                        }
                    }
                }
            ],
            "roleArn": "arn:aws:iam::493314881487:role/aws-service-role/ecs.amazonaws.com/AWSServiceRoleForECS",
            "events": [
                {
                    "id": "ae0bc545-fd2a-4678-84df-09cfbdc5d8bc",
                    "createdAt": 1590569152.945,
                    "message": "(service hello-world) has reached a steady state."
                },
                {
                    "id": "d5eeeaea-7af3-4e33-a2ab-e3c6fbf84b2c",
                    "createdAt": 1590569133.957,
                    "message": "(service hello-world) registered 1 targets in (target-group arn:aws:elasticloadbalancing:eu-central-1:493314881487:targetgroup/ecs-fargat-hello-world/0c505c5c320f4234)"
                },
                {
                    "id": "db23aff6-d96d-4845-b47e-85dade42411b",
                    "createdAt": 1590569102.574,
                    "message": "(service hello-world) has started 1 tasks: (task 79dd7879f97549fbb458d61b9ab436d2)."
                }
            ],
            "createdAt": 1590569101.303,
            "placementConstraints": [],
            "placementStrategy": [],
            "networkConfiguration": {
                "awsvpcConfiguration": {
                    "subnets": [
                        "subnet-0cbb958b213ee2f25",
                        "subnet-0a01a1bafc5a43d07"
                    ],
                    "securityGroups": [
                        "sg-0de8dc0f9116af675"
                    ],
                    "assignPublicIp": "ENABLED"
                }
            },
            "healthCheckGracePeriodSeconds": 600,
            "schedulingStrategy": "REPLICA",
            "enableECSManagedTags": true,
            "propagateTags": "NONE"
        }
    ],
    "failures": []
}
```

Security Group must grant access from ELB to fargate service (better: self-referencing security group, assign to service and ELB):

```json
 {
            "Description": "2020-05-27T08:31:49.837Z",
            "GroupName": "hello--5504",
            "IpPermissions": [
                {
                    "FromPort": 80,
                    "IpProtocol": "tcp",
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0"
                        }
                    ],
                    "Ipv6Ranges": [],
                    "PrefixListIds": [],
                    "ToPort": 80,
                    "UserIdGroupPairs": []
                }
            ],
            "OwnerId": "493314881487",
            "GroupId": "sg-0de8dc0f9116af675",
            "IpPermissionsEgress": [
                {
                    "IpProtocol": "-1",
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0"
                        }
                    ],
                    "Ipv6Ranges": [],
                    "PrefixListIds": [],
                    "UserIdGroupPairs": []
                }
            ],
            "VpcId": "vpc-06296a2d8e5fe7691"
        }
```