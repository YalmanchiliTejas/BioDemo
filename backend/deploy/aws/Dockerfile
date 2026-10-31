# AWS Lambda image for the platform API. Build context: backend/
#   docker build --platform linux/arm64 -f deploy/aws/Dockerfile -t biodemo-api .
# (deploy.sh does this through SAM.) Only src/ and the sample CMO packages are
# copied; see Dockerfile.dockerignore.
FROM public.ecr.aws/lambda/python:3.13

COPY deploy/aws/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY src ${LAMBDA_TASK_ROOT}/src
COPY benchmarks/cmo_ingestion/demo ${LAMBDA_TASK_ROOT}/benchmarks/cmo_ingestion/demo

# Import once at build time so a missing dependency fails the build, not the first request.
RUN cd ${LAMBDA_TASK_ROOT} && python -c "import src.lifesci.aws_lambda, src.lifesci.api, src.manufacturing_data.cmo.api"

CMD ["src.lifesci.aws_lambda.handler"]
