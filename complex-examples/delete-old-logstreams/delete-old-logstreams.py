from datetime import datetime
from time import sleep

import boto3
from botocore.config import Config


def delete_old_log_streams(aws_session):
    """
    Delete log streams which are empty and its lifetime exceeds the retention time.
    This code has been heavily inspired by https://aws.amazon.com/de/blogs/mt/delete-empty-cloudwatch-log-streams/

    :param aws_session: The AWS session
    """
    now = datetime.now().timestamp() * 1000
    cloudwatch_client = aws_session.client("logs", config=Config(retries=dict(max_attempts=10, mode="standard")))
    log_groups = [log_group
                  for log_groups_page in cloudwatch_client.get_paginator("describe_log_groups").paginate()
                  for log_group in log_groups_page["logGroups"]
                  if "retentionInDays" in log_group]

    log_streams_paginator = cloudwatch_client.get_paginator("describe_log_streams")
    for log_group in log_groups:
        log_streams = [log_stream
                       for log_streams_page in log_streams_paginator.paginate(logGroupName=log_group["logGroupName"])
                       for log_stream in log_streams_page["logStreams"]
                       if "lastEventTimestamp" in log_stream and log_stream["storedBytes"] == 0]
        for log_stream in log_streams:
            diff_millis = now - log_stream["lastIngestionTime"]
            diff_days = diff_millis / (1000*86400)
            if diff_days > log_group["retentionInDays"]:
                print(f'Deleting log stream {log_group["logGroupName"]}/{log_stream["logStreamName"]}')
                cloudwatch_client.delete_log_stream(logGroupName=log_group["logGroupName"],
                                                    logStreamName=log_stream["logStreamName"])
                sleep(0.2)  # prevent rate exceeded errors


def lambda_handler(event, context):
    aws_session = boto3.Session()
    delete_old_log_streams(aws_session)

    return "Ok"
