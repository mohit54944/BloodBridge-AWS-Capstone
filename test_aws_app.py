import os
import boto3
from moto import mock_aws

# 1. Mock Credentials (Must be set BEFORE app_aws is imported)
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
os.environ['AWS_SECURITY_TOKEN'] = 'testing'
os.environ['AWS_SESSION_TOKEN'] = 'testing'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

# 2. Start Moto Mock
mock = mock_aws()
mock.start()

# 3. Import your specific app
import app_aws
from app_aws import app

def setup_bloodbridge_infrastructure():
    print(">>> Creating Mocked BloodBridge Resources...")
    
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    sns = boto3.client('sns', region_name='us-east-1')

    # Users Table (Partition Key: username)
    dynamodb.create_table(
        TableName='Users',
        KeySchema=[{'AttributeName': 'username', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'username', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
    )

    # AdminUsers Table (Partition Key: username)
    dynamodb.create_table(
        TableName='AdminUsers',
        KeySchema=[{'AttributeName': 'username', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'username', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
    )

    # BloodInventory Table (Partition Key: blood_type)
    dynamodb.create_table(
        TableName='BloodInventory',
        KeySchema=[{'AttributeName': 'blood_type', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'blood_type', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
    )

    # BloodRequests Table (Partition Key: id)
    dynamodb.create_table(
        TableName='BloodRequests',
        KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
    )

    # Pre-fill Mock Inventory (so the dashboard isn't empty)
    inventory_table = dynamodb.Table('BloodInventory')
    blood_types = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]
    for bt in blood_types:
        inventory_table.put_item(Item={'blood_type': bt, 'quantity': 10})

    # SNS Setup
    topic = sns.create_topic(Name='aws_capstone_topic')
    app_aws.SNS_TOPIC_ARN = topic['TopicArn']
    
    print(f">>> Mock Environment Ready. SNS Topic ARN: {app_aws.SNS_TOPIC_ARN}")

if __name__ == '__main__':
    try:
        setup_bloodbridge_infrastructure()
        print("\n>>> Starting Flask Server at http://localhost:5000")
        print(">>> Testing Tip: Use these mock credentials to login after signing up.")
        # use_reloader=False is mandatory to keep the mock state alive
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    finally:
        mock.stop()