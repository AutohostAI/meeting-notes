FROM public.ecr.aws/lambda/python:3.13

# Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy function code
COPY src/server.py ${LAMBDA_TASK_ROOT}
COPY src/libs ${LAMBDA_TASK_ROOT}/libs
COPY credentials.json ${LAMBDA_TASK_ROOT}

# Expose port 8080
EXPOSE 8080

# Set the CMD
CMD ["server.handler"]