"""
Generate ande deploy a CloudWatch Dashboard dynamically
"""
import json
import logging

import boto3
import click
from boto3.session import Session

logging.getLogger().setLevel(logging.INFO)
logging.getLogger("botocore").setLevel(logging.CRITICAL)
logging.getLogger("boto3").setLevel(logging.CRITICAL)

METRIC_NAMES = [
    "Failed",
    "TotalDurationInMs",
    "DnsLookUpTimeInMs",
    "TcpConnectionTimeInMs",
    "TlsHandshakeTimeInMs",
    "RequestSentTimeInMs",
    "FirstByteTimeInMs",
    "ContentTransferTimeInMs",
]
METRIC_DIMENSION = "Id"


def read_json_file(filename):
    with open(filename) as f:
        return json.load(f)


def new_line_widget(x, y, height, width, region, dimension_ids, metric_index, metric_namespace):
    metrics = []
    for id in dimension_ids:
        if len(metrics) == 0:
            metrics.append([metric_namespace, METRIC_NAMES[metric_index], METRIC_DIMENSION, id])
        else:
            metrics.append(["...", id])

    return {
        "type": "metric",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "properties": {
            "view": "timeSeries",
            "stacked": False,
            "metrics": metrics,
            "region": region,
            "yAxis": {
                "left": {
                    "min": 0
                }
            }
        }
    }


def generate_dashboard_body(dimension_ids, region, metric_namespace):
    body = {"widgets": []}
    cols = 4
    rows = 2
    width = 6  # for cols = 4
    height = 6
    metric_index = 0

    for y in range(0, rows*height, height):
        for x in range(0, cols*width, width):
            body["widgets"].append(new_line_widget(x, y, width, height, region, dimension_ids, metric_index, metric_namespace))
            metric_index += 1

    return body


@click.command(help="Create CloudWatch Dashboard Body json file.")
@click.option("--dashboard-name", "-n", required=True, help="The name of the dashboard.")
@click.option("--input-file", "-f", required=True, help="URLs input file (json).")
@click.option("--metric-namespace", "-m", default="CurlPerformance", show_default=True, help="The name of the Metric Namespace.")
@click.option("--profile", "-p", help="AWS profile name.")
@click.option("--region", "-r", required=True, help="AWS Region. All dashboards in your account are global, not region-specific.")
def main(dashboard_name, input_file, metric_namespace, profile, region):

    dimension_ids = read_json_file(input_file).keys()

    body = generate_dashboard_body(dimension_ids, region, metric_namespace)

    if profile:
        client = Session(profile_name=profile).client("cloudwatch")
    else:
        client = boto3.client("cloudwatch")

    resp = client.put_dashboard(
        DashboardName=dashboard_name,
        DashboardBody=json.dumps(body)
    )
    if resp["ResponseMetadata"]["HTTPStatusCode"] != 200:
        raise Exception("Failed to create CloudWatch Dashboard")


if __name__ == "__main__":
     main()
