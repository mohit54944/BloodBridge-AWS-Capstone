import boto3

# Ensure your local AWS CLI is configured or this is run on an EC2 with an IAM Role
REGION = 'us-east-1'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
inventory_table = dynamodb.Table('BloodInventory')

blood_types = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]

def initialize_inventory():
    print("Initializing BloodBridge Inventory...")
    for bt in blood_types:
        # We start each type with 0 units or a small default value
        inventory_table.put_item(
            Item={
                'blood_type': bt,
                'quantity': 0  # Starting fresh for the capstone
            }
        )
        print(f"Created entry for {bt}")

if __name__ == "__main__":
    initialize_inventory()