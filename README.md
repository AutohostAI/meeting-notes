# AI-Generated Meeting Notes for Google Meet

Summarize Google Meet calls using GPT-3.5.

## How it works

1. User enables [transcripts](https://support.google.com/meet/answer/12849897?hl=en) during a Google Meet call.
2. When meeting ends, Google Meet will upload a transcript to the user's Google Drive.
3. Google Drive sends a webhook notifying us that a new file was created.
4. We download the transcript from Google Drive and send it to OpenAI to summarize.
5. We send the summary to the meeting attendees via email.

>This project uses OpenAI's [gpt-3.5-turbo-16k](https://platform.openai.com/docs/models/gpt-3-5) model.

See [demo](#demo) below for an example.

## Build and deploy

Steps:

1. Create a service account for Google Drive.
2. Build the container image.
3. Deploy using CloudFormation.

### Create a service account on Google Cloud

Create a **Service Account** in Google Cloud and download the JSON key file.
See [this](https://docs.mithi.com/home/preparation-for-googleworkspace-by-enabling-domain-wide-delegation-using-oauth-service) or [this](https://medium.com/swlh/google-drive-push-notification-b62e2e2b3df4) example for more details.

Save the JSON key to the `credentials.json` file.

The Docker build specification will copy the `credentials.json` file to the container image.

>Remember to enable **Domain Wide Delegation** for the Service Account to access Google Drive files owned by other users.


### Building the container image

> This build example uses AWS ECR to store the container image. However, you can use any container registry.
> 
> Replace `xxx.dkr.ecr.us-east-1.amazonaws.com` with your container registry.

Build the Docker image:

```bash
docker build -t meeting-notes .
```

Log into AWS ECR:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin xxx.dkr.ecr.us-east-1.amazonaws.com
```

Tag the image:

```bash
docker tag meeting-notes:latest xxx.dkr.ecr.us-east-1.amazonaws.com/meeting-notes:latest
```

Push the image to ECR:

```bash
docker push xxx.dkr.ecr.us-east-1.amazonaws.com/meeting-notes:latest
```

### Deploying the API and worker

Create a CloudFormation parameters file:

```bash
cp stack-params.json stack-params-prod.json
```

Update the `stack-params-prod.json` file with values for the following parameters:

- Architecture
- ApiContainerImageUri
- ApiContainerImageTag
- OpenaiApiKey
- OpenaiOrgId
- StageName
- MailgunApiKey
- MailgunDomain
- S3Bucket
- WorkspaceEmails *(comma separated list of emails belonging to users in the Google Workspace)*

Deploy CloudFormation template using `aws-cli`:

```bash
aws cloudformation create-stack \
    --stack-name meeting-notes-prod \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags Key=service,Value=meeting-notes Key=Environment,Value=prod \
    --parameters file://$(pwd)/stack-params-prod.json \
    --template-body file://$(pwd)/cloudformation.yaml --profile default
```

Update CloudFormation template using `aws-cli`:

```bash
aws cloudformation update-stack \
    --stack-name meeting-notes-prod \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags Key=service,Value=meeting-notes Key=Environment,Value=prod \
    --parameters file://$(pwd)/stack-params-prod.json \
    --template-body file://$(pwd)/cloudformation.yaml --profile default
```

## Test lambda locally

Build the container image first.

Create a `.env` file with the following contents:

```bash
AWS_DEFAULT_REGION=us-east-1
OPENAI_API_KEY=xxx
OPENAI_ORG_ID=org-xxx
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
MAILGUN_API_KEY=xxx
MAILGUN_DOMAIN=xxx.xyz
S3_BUCKET=xxx
LAMBDA_FUNCTION_NAME=meeting-notes-prod-api
````

Build and run the image:

```bash
docker build -t meeting-notes . && docker run -p 9000:8080 --env-file=.env --rm meeting-notes
```

Open a new terminal window, and use `curl` to test the following endpoints.

Webhook event from Google Drive when a document is created:

```bash
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"body":{"id":"change-me","owner_email":"change-me@example.com","title":"Test - Transcript"}}'
```

SQS event for worker to summarize the meeting transcript:

```bash
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"Records":[{"messageId":"xxxx-xx-xx-xx-xxxx","body":"{\"title\":\"Example Meeting (2023-05-26 12:38 GMT-4) - Transcript\",\"id\":\"change-me\",\"link\":\"https://docs.google.com/document/d/change-me/edit?usp=drivesdk\",\"owner_email\":\"change-me@example.com\"}","attributes":{"ApproximateReceiveCount":"1","AWSTraceHeader":"Root=1-6470f9b0-xxxx;Parent=xxxx;Sampled=0;Lineage=85108a56:0","SentTimestamp":"1685125554295","SenderId":"change-me:meeting-notes-prod-api","ApproximateFirstReceiveTimestamp":"1685125554296"},"messageAttributes":{},"md5OfBody":"11268099d001110f04757778362ddb11","eventSource":"aws:sqs","eventSourceARN":"arn:aws:sqs:us-east-1:change-me:meeting-notes-prod-prod-queue","awsRegion":"us-east-1"}]}'
```

## Demo

Example email sent to meeting attendees:

```text
Git Bootcamp (2023-05-29 14:03 GMT-4) - Transcript

Attendees:
Gilfoyle, Dinesh, Richard Hendricks, Jared Dunn, Monica Hall, Erlich Bachman 

Summary:
In the workshop, Gilfoyle provided an in-depth explanation of Git, focusing on the differences 
between merging and rebasing. He emphasized the safety of using git fetch for downloading updates 
from the remote repository and used visual aids to illustrate the differences between merging and rebasing. 
He advised against squashing commits from develop to master to avoid confusion and duplication. 
He also stressed the importance of updating branches and creating feature branches off of develop, 
recommending the rule of two for branching off feature branches and merging changes into develop in 
small increments. He introduced the concept of WIP or draft PRs for ongoing work and the need for a clear 
team workflow. He also touched on the interactive rebase command and its options, and concluded with a 
brief discussion on git log and its search options.

Key Decisions:
- Git fetch should be used for safely downloading updates from the remote repository.
- Squashing commits from develop to master should be avoided to prevent confusion and duplication.
- The rule of two should be followed for branching off feature branches and changes should be merged into develop in small pieces.
- A clear workflow should be established for the team, including the use of WIP or draft PRs for ongoing work.

Next Steps:
- Team members should familiarize themselves with the differences between merging and rebasing.
- Team members should practice using git fetch for downloading updates.
- Team members should avoid squashing commits from develop to master.
- Team members should follow the rule of two for branching off feature branches and merge changes into develop in small increments.
- Team members should use WIP or draft PRs for ongoing work.
- Team members should establish a clear workflow.
- Team members should familiarize themselves with the interactive rebase command and its options.
- Team members should learn how to use git log and its search options.

Full transcript:
https://docs.google.com/document/d/xxxxxx/edit?usp=drivesdk

---
Sent by Meeting Notes AI 🤖
```