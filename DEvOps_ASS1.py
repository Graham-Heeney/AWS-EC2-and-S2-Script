import boto3
import json
import time
import subprocess



#------------------------------------------VARIABLES-------------------------------------------

# S3 bucket details
BUCKET_NAME = f'graham-heeney-bucket-{int(time.time())}'  # Unique bucket name.
OBJECT_NAME = 'index.html'  # File to upload.
IMAGE_NAME = 'SETU-Logo.png'  # Image to include in HTML.

# EC2 instance settings
IMAGE_ID = 'ami-0ebfd941bbafe70c6'  # AMI for EC2.
MIN_COUNT = 1
MAX_COUNT = 1
INSTANCE_TYPE = 't2.nano'
SECURITY_GROUPS_IDS = ['sg-07054770e83af86f2']
KEY_NAME = '12345key'
SCRIPT_NAME = 'monitoring.sh'
WAIT_TIME = 30  # Wait time before SSH.

# File for storing URLs
FILENAME = "gheeney-websites.txt"


#--------------------------------SETTING UP S3 BUCKET----------------------------------------

# Initialize S3 resource and client
s3 = boto3.resource('s3')
s3client = boto3.client('s3')

# Create bucket and configure it for public access
s3.create_bucket(Bucket=BUCKET_NAME)
s3client.delete_public_access_block(Bucket=BUCKET_NAME)

# Set public read access
bucket_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": ["s3:GetObject"],
            "Resource": f"arn:aws:s3:::{BUCKET_NAME}/*"
        }
    ]
}
s3.Bucket(BUCKET_NAME).Policy().put(Policy=json.dumps(bucket_policy))

# Create and upload HTML and image to the bucket
index_content = f"""
<html>
  <head><title>Assignment S3 Bucket web page</title></head>
  <body>
    <h1>This web page is hosted on s3</h1>
    <img src="https://{BUCKET_NAME}.s3.amazonaws.com/{IMAGE_NAME}" alt="My Image"/> 
  </body>
</html>
"""
with open(OBJECT_NAME, 'w') as f:
    f.write(index_content)

s3.Object(BUCKET_NAME, OBJECT_NAME).put(Body=open(OBJECT_NAME, 'rb'), ContentType='text/html')
s3.Object(BUCKET_NAME, IMAGE_NAME).put(Body=open(f'/home/graham/{IMAGE_NAME}', 'rb'), ContentType='image/png')

print(f"S3 bucket {BUCKET_NAME} setup complete and objects uploaded!")

# Write public URL to file
url1 = f"https://{BUCKET_NAME}.s3.amazonaws.com/{OBJECT_NAME}"
with open(FILENAME, 'w') as file:
    file.write(url1 + '\n')

print(f"URL written to {FILENAME}")


#------------------------------------SETTING UP EC2 INSTANCE------------------------------------

# Launch EC2 instance
ec2 = boto3.resource('ec2')
new_instances = ec2.create_instances(
    ImageId=IMAGE_ID,
    MinCount=MIN_COUNT,
    MaxCount=MAX_COUNT,
    InstanceType=INSTANCE_TYPE,
    SecurityGroupIds=SECURITY_GROUPS_IDS,
    UserData="""#!/bin/bash
            yum update -y
            yum install httpd -y
            systemctl enable httpd
            systemctl start httpd

            TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"`
            INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-id)
            PRIVATE_IP=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/local-ipv4)
            INSTANCE_TYPE=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-type)
            AVAILABILITY_ZONE=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/placement/availability-zone)

            echo "<html>
                    <h1>Welcome to Your EC2 Instance</h1>
                    <p><b>Instance ID:</b> $INSTANCE_ID</p>
                    <p><b>Private IP:</b> $PRIVATE_IP</p>
                    <p><b>Instance Type:</b> $INSTANCE_TYPE</p>
                    <p><b>Availability Zone:</b> $AVAILABILITY_ZONE</p>
                    <p><b>Additional Content:</b> This is your instance's meta data!</p>
                    </html>" > /var/www/html/index.html
            """,
    KeyName=KEY_NAME,
    TagSpecifications=[{
        'ResourceType': 'instance',
        'Tags': [{'Key': 'Name', 'Value': 'Web server'}]
    }]
)

# Get instance details
instance = new_instances[0]
instance.reload()
public_ip = instance.public_ip_address
print(f"Instance {instance.id} launched and running!")

# Write EC2 instance URL to file      https://stackoverflow.com/questions/33289247/how-to-write-links-to-a-text-file
public_dns = instance.public_dns_name
ec2_url = f"http://{public_dns}"

with open(FILENAME, 'a') as file:
    file.write(ec2_url + '\n')

print(f"URLs written to {FILENAME}")

#Wait before connecting to instance
time.sleep(WAIT_TIME)


#-------------------------------------------------Monitoring Script----------------------------------------------------------

# Transfer and run the monitoring script on the EC2 instance
scp_cmd = f"scp -o StrictHostKeyChecking=no -i {KEY_NAME}.pem {SCRIPT_NAME} ec2-user@{public_ip}:~"
chmod_cmd = f"ssh -i {KEY_NAME}.pem ec2-user@{public_ip} 'chmod 700 {SCRIPT_NAME}'"
run_script_cmd = f"ssh -i {KEY_NAME}.pem ec2-user@{public_ip} './{SCRIPT_NAME}'"
run_script_disk_usage = f"ssh -i {KEY_NAME}.pem ec2-user@{public_ip} 'df -h / | awk \"NR==2 {{print \\$5}}\"'"
run_script_uptime = f"ssh -i {KEY_NAME}.pem ec2-user@{public_ip} 'uptime'"

# Run commands
print("Running SCP command to transfer monitoring.sh...")
result = subprocess.run(scp_cmd, shell=True)
if result.returncode == 0:
    print("File transferred successfully!")

    print("Making script executable...")
    result = subprocess.run(chmod_cmd, shell=True)
    if result.returncode == 0:
        print("Script is now executable.")

        print("Executing the script on the EC2 instance...")
        result = subprocess.run(run_script_cmd, shell=True)
        if result.returncode == 0:
            print("Script executed successfully!")

            print("Checking instance uptime...")
            result = subprocess.run(run_script_uptime, shell=True)
            if result.returncode == 0:           
                print("Uptime check successful!")

                print("Monitoring disk usage...")
                result = subprocess.run(run_script_disk_usage, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"Disk usage: {result.stdout.strip()}")
                else:
                    print("Error monitoring disk usage.")
            else:
                print("Error checking uptime.")
        else:
            print("Error executing script.")
    else:
        print("Error making script executable.")
else:
    print("Error transferring file.")

