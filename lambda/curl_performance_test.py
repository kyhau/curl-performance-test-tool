import json
import logging
import os
import subprocess

import boto3

logging.getLogger().setLevel(logging.INFO)
logging.getLogger("botocore").setLevel(logging.CRITICAL)
logging.getLogger("boto3").setLevel(logging.CRITICAL)

BUCKET_NAME = os.environ.get("BUCKET_NAME")
DEFAULT_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
LOCAL_RUN = os.environ.get("LocalRun", "false")
METRIC_NAMESPACE = os.environ.get("METRIC_NAMESPACE", "CurlPerformance")

# Ref: https://speedtestdemon.com/a-guide-to-curls-performance-metrics-how-to-analyze-a-speed-test-result/
CURL_VARS = [
    "http_code",
    "time_namelookup",
    "time_connect",
    "time_appconnect",
    "time_pretransfer",
    "time_starttransfer",
    "time_total",
]
CURL_W_FORMAT = "\\n".join("%%{%s}" % v for v in CURL_VARS)

METRIC_NAMES = [
    "DnsLookUpTimeInMs",
    "TcpConnectionTimeInMs",
    "TlsHandshakeTimeInMs",
    "RequestSentTimeInMs",
    "FirstByteTimeInMs",
    "ContentTransferTimeInMs",
    "TotalDurationInMs",
]

cloudwatch_client = boto3.client("cloudwatch", region_name=DEFAULT_REGION)
s3_client = boto3.client("s3", region_name=DEFAULT_REGION)


def read_from_s3(bucket):
    account_id = boto3.client("sts").get_caller_identity().get("Account")
    content = s3_client.get_object(Bucket=bucket, Key=f"inputs/{account_id}-{DEFAULT_REGION}.json")["Body"]
    return json.loads(content.read())

INPUT_DATASET = read_from_s3(BUCKET_NAME)


def call_curl(url):
    args = ["curl", "-sSo", "/dev/null", "-k", "-w", CURL_W_FORMAT, url]

    try:
        output = subprocess.check_output(args, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        fail_lines = filter(lambda x: x.startswith("curl"), err.output.decode("utf-8").splitlines())
        logging.error(", ".join(fail_lines))
        if err.returncode == 6:
            # Could not resolve host
            return err.returncode, {}
        raise

    vars = dict(zip(CURL_VARS, output.decode("ascii").splitlines()))
    last_metric = 0
    metrics = []
    for metric in CURL_VARS[1:]:
        metric = round(float(vars[metric].replace(",", ".")) * 1000)
        metric = last_metric if metric == 0 else metric
        metrics.append(metric - last_metric)
        last_metric = metric

    metrics.append(last_metric)  # Total duration

    return int(vars["http_code"]), {METRIC_NAMES[i]: metrics[i] for i in range(len(metrics))}


def put_custom_metric_data(dimension_value, name, value, unit="None"):
    metric_data = {
        "Dimensions": [{
            "Name": "Id",
            "Value": dimension_value,
        }],
        "MetricName": name,
        "Unit": unit,
        "Value": value,
    }
    cloudwatch_client.put_metric_data(
        MetricData=[metric_data],
        Namespace=METRIC_NAMESPACE,
    )


def lambda_handler(event, context):
    results = INPUT_DATASET

    for id, item in INPUT_DATASET.items():
        status_code = None
        try:
            logging.info(f"Testing {id}: {item['Url']}")

            status_code, data = call_curl(url=item["Url"])

            logging.info(json.dumps(data, indent=2))

            if LOCAL_RUN == "false":
                for name, value in data.items():
                    put_custom_metric_data(id, name, value, "Milliseconds")

                if status_code < 200 or status_code >= 400:
                    put_custom_metric_data(id, "Failed", 1)

        except Exception as e:
            logging.error(e)
            status_code = 500
        finally:
            results[id].update({"StatusCode": status_code})

    logging.info(json.dumps(results, indent=2))
    return {
        "body": json.dumps(results),
        "statusCode": 200,
    }
