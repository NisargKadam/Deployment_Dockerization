"""Copyable cloud deployment walkthroughs embedded in the standalone guide."""

AZURE = [
    (
        "1. Install, sign in, and select the subscription",
        "Run blocks in order in the same Bash terminal, from Deployment_Dockerization. On macOS with Homebrew, install the CLI below; on Linux use Microsoft's Azure CLI installer. Replace the subscription ID. These commands provision billable cloud resources.",
        r"""# macOS only, if Azure CLI is missing
brew install azure-cli
# Use Bash for all remaining blocks (also available through WSL on Windows).
bash
if [ -d Deployment_Dockerization ]; then cd Deployment_Dockerization; fi
ls Dockerfile
az login
az account list --output table
az account set --subscription "YOUR_SUBSCRIPTION_ID"
az account show --output table
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.ManagedIdentity --wait
AZ_LOCATION=southeastasia
AZ_SUFFIX=$(date +%s)
AZ_RG="humanizer-demo-$AZ_SUFFIX"
AZ_ACR="humanizer$AZ_SUFFIX"
AZ_APP=humanizer
AZ_ENV=humanizer-env
AZ_TAG=1.0""",
    ),
    (
        "2. Create the registry and build the image",
        "The remote build targets Linux AMD64, including when your laptop is Apple Silicon. The registry name must be globally unique; change AZ_ACR if it is already taken.",
        r"""az group create --name "$AZ_RG" --location "$AZ_LOCATION"
az acr create --resource-group "$AZ_RG" --name "$AZ_ACR" --sku Basic --role-assignment-mode rbac
az acr config authentication-as-arm update -r "$AZ_ACR" --status enabled
az acr build --registry "$AZ_ACR" --image "humanizer-lab:$AZ_TAG" --platform linux/amd64 .
AZ_REGISTRY=$(az acr show -n "$AZ_ACR" --query loginServer -o tsv)
AZ_ACR_ID=$(az acr show -n "$AZ_ACR" --query id -o tsv)""",
    ),
    (
        "3. Grant image-pull access and deploy",
        "Your account needs permission to create role assignments. If registry access is denied immediately after the role assignment, allow a few minutes for propagation and retry the create command. The app uses managed identity, with no registry password.",
        r"""az identity create --name humanizer-pull --resource-group "$AZ_RG"
AZ_IDENTITY=$(az identity show -g "$AZ_RG" -n humanizer-pull --query id -o tsv)
AZ_PRINCIPAL=$(az identity show -g "$AZ_RG" -n humanizer-pull --query principalId -o tsv)
az role assignment create --assignee-object-id "$AZ_PRINCIPAL" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$AZ_ACR_ID"
az containerapp env create --name "$AZ_ENV" --resource-group "$AZ_RG" --location "$AZ_LOCATION"
az containerapp create --name "$AZ_APP" --resource-group "$AZ_RG" \
  --environment "$AZ_ENV" --image "$AZ_REGISTRY/humanizer-lab:$AZ_TAG" \
  --user-assigned "$AZ_IDENTITY" --registry-identity "$AZ_IDENTITY" \
  --registry-server "$AZ_REGISTRY" --ingress external --target-port 8000 \
  --cpu 0.5 --memory 1Gi --min-replicas 1 --max-replicas 1 \
  --env-vars PORT=8000 ENVIRONMENT=azure APP_MODE=demo ENABLE_DEMO_SCENARIOS=true LANGSMITH_TRACING=false""",
    ),
    (
        "4. Get the HTTPS URL, verify, and inspect logs",
        "Open AZ_URL in your browser. Demo mode needs no OpenAI or LangSmith key. The health endpoints check the app, not external provider connectivity.",
        r"""AZ_FQDN=$(az containerapp show -g "$AZ_RG" -n "$AZ_APP" --query properties.configuration.ingress.fqdn -o tsv)
AZ_URL="https://$AZ_FQDN"
echo "$AZ_URL"
curl --fail --retry 10 --retry-all-errors --retry-delay 3 "$AZ_URL/health"
curl --fail "$AZ_URL/ready"
curl --fail "$AZ_URL/humanize" -H 'Content-Type: application/json' \
  -d '{"text":"Furthermore, we utilize containers in order to deploy applications consistently."}'
az containerapp revision list -g "$AZ_RG" -n "$AZ_APP" -o table
az containerapp logs show -g "$AZ_RG" -n "$AZ_APP" --type console --tail 50""",
    ),
    (
        "5. Deploy a code update",
        "Use a new image tag to make the new revision identifiable. For startup failures, use system logs and check the latest revision status.",
        r"""AZ_TAG=1.1
az acr build --registry "$AZ_ACR" --image "humanizer-lab:$AZ_TAG" --platform linux/amd64 .
az containerapp update -g "$AZ_RG" -n "$AZ_APP" --image "$AZ_REGISTRY/humanizer-lab:$AZ_TAG"
az containerapp logs show -g "$AZ_RG" -n "$AZ_APP" --type system --tail 50""",
    ),
    (
        "6. Cleanup after the demo",
        "Run only when finished. This deletes the dedicated resource group, including the app, environment, registry/images, identity, and logging resources created in it. Keep the same terminal variables until cleanup is complete.",
        r'''az resource list --resource-group "$AZ_RG" --output table
az group delete --name "$AZ_RG" --yes
az group exists --name "$AZ_RG"''',
    ),
]

AWS = [
    (
        "1. Install, authenticate, and choose names",
        "Run blocks in order in the same Bash terminal, from Deployment_Dockerization. This is a complete classroom deployment using a task's public IP, restricted to your laptop's IP on port 8000. It uses HTTP and demo mode without secrets. For a shared live service, use an HTTPS load balancer and managed secrets. These commands create billable Fargate, registry, logging, and public IPv4 resources. AWS permissions must include ECR, ECS, EC2 networking, IAM role creation/PassRole, and CloudWatch Logs.",
        r"""# macOS only, if AWS CLI is missing
brew install awscli
bash
if [ -d Deployment_Dockerization ]; then cd Deployment_Dockerization; fi
ls Dockerfile
# First-time IAM Identity Center setup; use your organization's SSO details.
aws configure sso --profile humanizer-demo
export AWS_PROFILE=humanizer-demo
aws sso login
# If your CLI is already authenticated another way, use that profile instead.
export AWS_REGION=ap-southeast-1
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""
aws sts get-caller-identity
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_DEMO="humanizer-$(date +%s)"
AWS_CLUSTER="$AWS_DEMO"
AWS_SERVICE=humanizer
AWS_ROLE="$AWS_DEMO-execution"
AWS_REPO="$AWS_DEMO"
AWS_LOG_GROUP="/ecs/$AWS_DEMO"
AWS_REGISTRY="$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
AWS_IMAGE="$AWS_REGISTRY/$AWS_REPO:1.0"
AWS_WORK=$(mktemp -d)
# Docker Desktop must be running for the image build.
docker info >/dev/null""",
    ),
    (
        "2. Create ECR and push the image",
        "Build explicitly for Linux AMD64 to match the task definition. These examples use a standard AWS commercial region.",
        r"""aws ecr create-repository --repository-name "$AWS_REPO" --image-scanning-configuration scanOnPush=true
aws ecr get-login-password | docker login --username AWS --password-stdin "$AWS_REGISTRY"
docker buildx build --platform linux/amd64 -t "$AWS_IMAGE" --push .""",
    ),
    (
        "3. Create a dedicated VPC and public subnet",
        "No default VPC is required. The internet route and public task IP allow ECR pulls and outbound HTTPS. Only your current public IPv4 address can reach the app. If your VPN/network changes, update the security-group rule.",
        r'''AWS_VPC=$(aws ec2 create-vpc --cidr-block 10.42.0.0/16 --query Vpc.VpcId --output text)
aws ec2 create-tags --resources "$AWS_VPC" --tags "Key=Name,Value=$AWS_DEMO"
aws ec2 modify-vpc-attribute --vpc-id "$AWS_VPC" --enable-dns-support '{"Value":true}'
aws ec2 modify-vpc-attribute --vpc-id "$AWS_VPC" --enable-dns-hostnames '{"Value":true}'
AWS_SUBNET=$(aws ec2 create-subnet --vpc-id "$AWS_VPC" --cidr-block 10.42.1.0/24 --query Subnet.SubnetId --output text)
AWS_IGW=$(aws ec2 create-internet-gateway --query InternetGateway.InternetGatewayId --output text)
aws ec2 attach-internet-gateway --internet-gateway-id "$AWS_IGW" --vpc-id "$AWS_VPC"
AWS_ROUTE=$(aws ec2 create-route-table --vpc-id "$AWS_VPC" --query RouteTable.RouteTableId --output text)
aws ec2 create-route --route-table-id "$AWS_ROUTE" --destination-cidr-block 0.0.0.0/0 --gateway-id "$AWS_IGW"
AWS_ASSOC=$(aws ec2 associate-route-table --route-table-id "$AWS_ROUTE" --subnet-id "$AWS_SUBNET" --query AssociationId --output text)
AWS_SG=$(aws ec2 create-security-group --group-name "$AWS_DEMO" --description 'Humanizer classroom access' --vpc-id "$AWS_VPC" --query GroupId --output text)
AWS_MY_IP=$(curl -4 -fsS https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id "$AWS_SG" --protocol tcp --port 8000 --cidr "$AWS_MY_IP/32"''',
    ),
    (
        "4. Create the execution role and log group",
        "The execution role lets ECS pull the image and write logs. The application requires no separate task role for this demo. IAM permissions can take a short time to propagate; retry service creation if the role is initially rejected.",
        r'''cat > "$AWS_WORK/trust.json" <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
aws iam create-role --role-name "$AWS_ROLE" --assume-role-policy-document "file://$AWS_WORK/trust.json"
aws iam attach-role-policy --role-name "$AWS_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam wait role-exists --role-name "$AWS_ROLE"
AWS_ROLE_ARN=$(aws iam get-role --role-name "$AWS_ROLE" --query Role.Arn --output text)
aws logs create-log-group --log-group-name "$AWS_LOG_GROUP"
aws logs put-retention-policy --log-group-name "$AWS_LOG_GROUP" --retention-in-days 7
aws ecs create-cluster --cluster-name "$AWS_CLUSTER"''',
    ),
    (
        "5. Register the task and create the Fargate service",
        "This explicitly supplies the ECS health check; ECS does not inherit it from the image. Keep the generated task JSON for updates. The service maintains one running task.",
        r'''cat > "$AWS_WORK/task.json" <<JSON
{
  "family": "$AWS_DEMO",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "$AWS_ROLE_ARN",
  "runtimePlatform": {"cpuArchitecture": "X86_64", "operatingSystemFamily": "LINUX"},
  "containerDefinitions": [{
    "name": "humanizer",
    "image": "$AWS_IMAGE",
    "essential": true,
    "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
    "environment": [
      {"name":"PORT","value":"8000"},
      {"name":"ENVIRONMENT","value":"aws"},
      {"name":"APP_MODE","value":"demo"},
      {"name":"ENABLE_DEMO_SCENARIOS","value":"true"},
      {"name":"LANGSMITH_TRACING","value":"false"}
    ],
    "healthCheck": {
      "command": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"],
      "interval": 30, "timeout": 5, "retries": 3, "startPeriod": 30
    },
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {"awslogs-group":"$AWS_LOG_GROUP", "awslogs-region":"$AWS_REGION", "awslogs-stream-prefix":"ecs"}
    }
  }]
}
JSON
AWS_TASK_DEF=$(aws ecs register-task-definition --cli-input-json "file://$AWS_WORK/task.json" --query taskDefinition.taskDefinitionArn --output text)
aws ecs create-service --cluster "$AWS_CLUSTER" --service-name "$AWS_SERVICE" \
  --task-definition "$AWS_TASK_DEF" --desired-count 1 --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$AWS_SUBNET],securityGroups=[$AWS_SG],assignPublicIp=ENABLED}" \
  --deployment-configuration 'deploymentCircuitBreaker={enable=true,rollback=true},maximumPercent=200,minimumHealthyPercent=100'
aws ecs wait services-stable --cluster "$AWS_CLUSTER" --services "$AWS_SERVICE"''',
    ),
    (
        "6. Discover the URL, verify, and read logs",
        "Open AWS_URL on this laptop. The public IP changes when ECS replaces the task; rerun this block after deployments. If the waiter fails, inspect service events and stopped-task reasons before continuing.",
        r"""AWS_TASK=$(aws ecs list-tasks --cluster "$AWS_CLUSTER" --service-name "$AWS_SERVICE" --desired-status RUNNING --query 'taskArns[0]' --output text)
AWS_ENI=$(aws ecs describe-tasks --cluster "$AWS_CLUSTER" --tasks "$AWS_TASK" --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" --output text)
AWS_PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids "$AWS_ENI" --query 'NetworkInterfaces[0].Association.PublicIp' --output text)
AWS_URL="http://$AWS_PUBLIC_IP:8000"
echo "$AWS_URL"
curl --fail --retry 10 --retry-all-errors --retry-delay 3 "$AWS_URL/health"
curl --fail "$AWS_URL/ready"
curl --fail "$AWS_URL/humanize" -H 'Content-Type: application/json' \
  -d '{"text":"Furthermore, we utilize containers in order to deploy applications consistently."}'
aws logs tail "$AWS_LOG_GROUP" --since 10m
aws ecs describe-services --cluster "$AWS_CLUSTER" --services "$AWS_SERVICE" --query 'services[0].events[:5]' --output table
aws ecs list-tasks --cluster "$AWS_CLUSTER" --desired-status STOPPED
# For any stopped task ARN above:
# aws ecs describe-tasks --cluster "$AWS_CLUSTER" --tasks YOUR_STOPPED_TASK_ARN --query 'tasks[].{reason:stoppedReason,containers:containers[].reason}' """,
    ),
    (
        "7. Redeploy after editing code",
        "For this demo, repush the same tag and force ECS to pull it for new tasks. For release history, use unique image tags and register a new task-definition revision instead. Rerun step 6 to find the new IP.",
        r'''docker buildx build --platform linux/amd64 -t "$AWS_IMAGE" --push .
aws ecs update-service --cluster "$AWS_CLUSTER" --service "$AWS_SERVICE" --force-new-deployment
aws ecs wait services-stable --cluster "$AWS_CLUSTER" --services "$AWS_SERVICE"''',
    ),
    (
        "8. Cleanup after the demo",
        "Deletes only the resources identified by this session's variables, including the ECR images and logs. Keep this terminal open until cleanup finishes. Fargate network interfaces can take several minutes to disappear; if subnet deletion remains blocked, inspect the ENIs and rerun cleanup after release.",
        r'''aws ecs update-service --cluster "$AWS_CLUSTER" --service "$AWS_SERVICE" --desired-count 0
aws ecs wait services-stable --cluster "$AWS_CLUSTER" --services "$AWS_SERVICE"
aws ecs delete-service --cluster "$AWS_CLUSTER" --service "$AWS_SERVICE"
aws ecs wait services-inactive --cluster "$AWS_CLUSTER" --services "$AWS_SERVICE"
aws ecs delete-cluster --cluster "$AWS_CLUSTER"
aws ecs deregister-task-definition --task-definition "$AWS_TASK_DEF"
aws ecr delete-repository --repository-name "$AWS_REPO" --force
aws logs delete-log-group --log-group-name "$AWS_LOG_GROUP"
aws iam detach-role-policy --role-name "$AWS_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam delete-role --role-name "$AWS_ROLE"
aws ec2 disassociate-route-table --association-id "$AWS_ASSOC"
# Retry only this demo subnet while Fargate releases its network interface.
for attempt in $(seq 1 30); do
  aws ec2 delete-subnet --subnet-id "$AWS_SUBNET" && break
  sleep 10
done
aws ec2 delete-security-group --group-id "$AWS_SG"
aws ec2 delete-route-table --route-table-id "$AWS_ROUTE"
aws ec2 detach-internet-gateway --internet-gateway-id "$AWS_IGW" --vpc-id "$AWS_VPC"
aws ec2 delete-internet-gateway --internet-gateway-id "$AWS_IGW"
aws ec2 delete-vpc --vpc-id "$AWS_VPC"
# Local JSON files contain no API keys and may now be removed.
rm "$AWS_WORK/trust.json" "$AWS_WORK/task.json"
rmdir "$AWS_WORK"''',
    ),
]


def render_steps(steps, code):
    """Use the guide's existing escaped code blocks and copy buttons."""
    return "".join(
        f"<h3>{title}</h3><p>{description}</p>" + code(command, "Bash · run in order")
        for title, description, command in steps
    )
