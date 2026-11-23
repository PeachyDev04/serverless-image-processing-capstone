# Serverless Image Processing Pipeline

This project takes a JPG or PNG from a private S3 bucket, makes a PNG thumbnail that fits within 256 × 256 pixels, and saves it to a separate private S3 bucket. An upload starts the workflow through EventBridge. An API request can also start it for a file already in S3.

- Automatic path: S3 upload → EventBridge → Step Functions → Lambda → thumbnails bucket
- API path: API Gateway `POST /resize` → Step Functions → same Lambda and thumbnails bucket

## Files

- `lambda_function.py`: Downloads the original image, resizes it with Pillow, and saves the thumbnail.
- `requirements.txt`: Pillow dependency for the Lambda package.
- `workflow.asl.json`: Step Functions definition with Task, Choice, Succeed, and Fail states. Replace `${ResizeArn}` with your Lambda ARN when setting up the workflow.

## Set up on AWS

1. Create two private S3 buckets in the same region, one for originals and one for thumbnails. The project uses Ohio (`us-east-2`).
2. Create a Python 3.12 x86_64 Lambda function. Package the code and its Linux dependencies from a terminal with Python and pip:

   ```bash
   python3 -m pip install -r requirements.txt --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all: --target package
   cp lambda_function.py package/
   (cd package && zip -r ../lambda.zip .)
   ```

   Upload `lambda.zip` to Lambda and set the handler to `lambda_function.lambda_handler`. Set `ORIGINALS_BUCKET` and `THUMBNAILS_BUCKET` to the bucket names. Give the Lambda role CloudWatch logging access, `s3:GetObject` for the originals bucket objects, and `s3:PutObject` for the thumbnails bucket's `thumbnails/` prefix.
3. Create a Standard Step Functions state machine using `workflow.asl.json` with the Lambda ARN substituted. Give the workflow role permission to invoke the resize function. The Task calls Lambda, then the Choice checks `$.ok`. A false result or a Task error leads to `ResizeFailed`.
4. Enable EventBridge notifications on the originals bucket. On the default event bus, create a rule matching `aws.s3` Object Created events from that bucket for `.jpg`, `.jpeg`, and `.png` keys (case-insensitive). Target the workflow and pass the full event. The EventBridge target role needs `states:StartExecution` for this workflow.
5. In API Gateway, create a Regional REST API, add a `/resize` resource, and add a POST method. Use an AWS service integration for Step Functions, with integration HTTP method POST and action `StartExecution`. The integration role must trust `apigateway.amazonaws.com` and allow `states:StartExecution` on this workflow. Set passthrough to **Never**, then add an `application/json` integration request mapping template. Replace the example ARN below with your workflow ARN:

   ```vtl
   {
     "stateMachineArn": "arn:aws:states:REGION:ACCOUNT_ID:stateMachine:capstone-image-workflow",
     "input": "$util.escapeJavaScript($input.body).replaceAll("\\'","'")"
   }
   ```

   Set the method's authorization to `AWS_IAM` and deploy to the `dev` stage. A client calling the deployed endpoint must sign the POST request and have `execute-api:Invoke` permission for that method.

## Run the project

1. Upload a PNG named `test.png` to the originals bucket. Open the Step Functions executions list, confirm that the run succeeds, and find `thumbnails/test.png.png` in the thumbnails bucket. The output name keeps the original key and appends `.png`.
2. In **API Gateway → Resources → /resize → POST → Test**, set the header `Content-Type: application/json` and enter `{"key":"test.png"}` as the request body. The API returns an execution ARN when it starts the workflow. Open that execution in Step Functions and check for **Succeeded** and `"ok": true`. This console test runs the integration; sending a signed request to the deployed `/dev/resize` URL tests the live endpoint.
