import json
import os

import boto3


def handler(event, context):
    print(f"event:\n{event}")
    print(f"context:\n{context}")

    if 'open' in event['path']:
        sns_msg = "Mailbox door opened"
    elif 'ajar' in event['path']:
        sns_msg = "Mailbox door ajar"
    elif 'closed' in event['path']:
        sns_msg = "Mailbox door closed"
    else:
        sns_msg = "Unknown mailbox door state"

    client = boto3.client('sns')

    response = client.publish(
        TopicArn=os.environ['SNS_TOPIC_ARN'],
        Message=sns_msg,
    )

    if response['ResponseMetadata']['HTTPStatusCode'] != 200:
        raise RuntimeError

    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps('Snail mail ACK')
    }
