"""
Report generation for evaluation results.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def generate_html_report(report_data: dict[str, Any], output_path: Path) -> None:
    """
    Generate HTML evaluation report.

    Args:
        report_data: Evaluation report dictionary
        output_path: Path to save HTML file
    """
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>System Evaluation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 5px;
        }}
        .metric-card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .metric-name {{
            font-size: 1.2em;
            font-weight: bold;
            color: #2c3e50;
        }}
        .metric-value {{
            font-size: 1.5em;
            font-weight: bold;
            color: #27ae60;
        }}
        .metric-value.low {{
            color: #e74c3c;
        }}
        .metric-value.medium {{
            color: #f39c12;
        }}
        .details {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ecf0f1;
        }}
        .detail-row {{
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
        }}
        .detail-label {{
            color: #7f8c8d;
        }}
        .detail-value {{
            font-weight: 600;
        }}
        .target-met {{
            color: #27ae60;
        }}
        .target-missed {{
            color: #e74c3c;
        }}
        .overall-score {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            text-align: center;
            margin: 30px 0;
        }}
        .overall-score-value {{
            font-size: 3em;
            font-weight: bold;
            margin: 10px 0;
        }}
        .timestamp {{
            color: #95a5a6;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <h1>System Evaluation Report</h1>
    <p class="timestamp">Generated: {report_data.get('evaluation_summary', {}).get('timestamp', 'Unknown')}</p>
    
    <div class="overall-score">
        <h2>Overall Score</h2>
        <div class="overall-score-value">{report_data.get('overall_score', {}).get('score', 0.0):.1%}</div>
        <p>Based on {report_data.get('overall_score', {}).get('components', 0)} metric components</p>
    </div>
"""

    # Add metric sections
    metrics = report_data.get("metrics", {})
    for metric_name, metric_data in metrics.items():
        if "error" in metric_data:
            html_content += f"""
    <div class="metric-card">
        <div class="metric-header">
            <div class="metric-name">{metric_name.replace('_', ' ').title()}</div>
            <div class="metric-value low">Error</div>
        </div>
        <div class="details">
            <p>Error: {metric_data['error']}</p>
        </div>
    </div>
"""
            continue

        results = metric_data.get("results", {})
        if not results:
            continue

        # Determine main metric value
        main_value = 0.0
        main_label = "Score"
        if "coverage" in results:
            main_value = results["coverage"]
            main_label = "Coverage"
        elif "entity_to_chunk_coverage" in results:
            main_value = results["entity_to_chunk_coverage"]
            main_label = "Entity→Chunk"
        elif "average_precision_at_k" in results:
            main_value = results["average_precision_at_k"]
            main_label = "Precision@K"
        elif "graph_verification_rate" in results:
            main_value = results["graph_verification_rate"]
            main_label = "Verification"

        value_class = "low" if main_value < 0.5 else ("medium" if main_value < 0.7 else "")

        html_content += f"""
    <div class="metric-card">
        <div class="metric-header">
            <div class="metric-name">{metric_name.replace('_', ' ').title()}</div>
            <div class="metric-value {value_class}">{main_value:.1%}</div>
        </div>
        <div class="details">
"""

        # Add details
        for key, value in results.items():
            if key in ["target_", "meets_targets", "timestamp"]:
                continue
            if isinstance(value, (int, float)):
                html_content += f"""
            <div class="detail-row">
                <span class="detail-label">{key.replace('_', ' ').title()}:</span>
                <span class="detail-value">{value:.2f if isinstance(value, float) else value}</span>
            </div>
"""
            elif isinstance(value, bool):
                status_class = "target-met" if value else "target-missed"
                status_text = "✓" if value else "✗"
                html_content += f"""
            <div class="detail-row">
                <span class="detail-label">{key.replace('_', ' ').title()}:</span>
                <span class="detail-value {status_class}">{status_text}</span>
            </div>
"""

        # Add target information
        if "meets_targets" in results:
            html_content += """
            <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #ecf0f1;">
                <strong>Targets:</strong><br>
"""
            for target_name, met in results["meets_targets"].items():
                status_class = "target-met" if met else "target-missed"
                status_text = "✓ Met" if met else "✗ Not Met"
                html_content += f"""
                <span class="{status_class}">{target_name.replace('_', ' ').title()}: {status_text}</span><br>
"""
            html_content += """
            </div>
"""

        html_content += """
        </div>
    </div>
"""

    html_content += """
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html_content)
    logger.info(f"HTML report saved to {output_path}")


def generate_json_report(report_data: dict[str, Any], output_path: Path) -> None:
    """
    Generate JSON evaluation report.

    Args:
        report_data: Evaluation report dictionary
        output_path: Path to save JSON file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report_data, f, indent=2, default=str)
    logger.info(f"JSON report saved to {output_path}")


def generate_csv_metrics(report_data: dict[str, Any], output_path: Path) -> None:
    """
    Generate CSV file with metrics for tracking over time.

    Args:
        report_data: Evaluation report dictionary
        output_path: Path to save CSV file
    """
    import csv

    timestamp = report_data.get("evaluation_summary", {}).get("timestamp", datetime.utcnow().isoformat())
    overall_score = report_data.get("overall_score", {}).get("score", 0.0)

    rows = [["timestamp", "metric", "value", "target_met"]]

    # Add overall score
    rows.append([timestamp, "overall_score", overall_score, ""])

    # Add individual metrics
    metrics = report_data.get("metrics", {})
    for metric_name, metric_data in metrics.items():
        if "error" in metric_data:
            continue

        results = metric_data.get("results", {})
        for key, value in results.items():
            if key in ["meets_targets", "timestamp", "per_query_results"]:
                continue
            if isinstance(value, (int, float, bool)):
                target_met = ""
                if "meets_targets" in results and key in results["meets_targets"]:
                    target_met = results["meets_targets"][key]
                rows.append([timestamp, f"{metric_name}.{key}", value, target_met])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    logger.info(f"CSV metrics saved to {output_path}")

