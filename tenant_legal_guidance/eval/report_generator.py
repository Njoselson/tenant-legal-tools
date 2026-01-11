"""
Report generation for evaluation results.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate evaluation reports in HTML and JSON formats."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def generate_html_report(self, results: dict[str, Any], filename: str = "evaluation_report.html") -> Path:
        """
        Generate HTML evaluation report.

        Args:
            results: Evaluation results dictionary
            filename: Output filename

        Returns:
            Path to generated HTML file
        """
        output_path = self.output_dir / filename

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
        .summary-card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-card {{
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .metric-name {{
            font-weight: bold;
            color: #2c3e50;
        }}
        .metric-value {{
            font-size: 1.2em;
            font-weight: bold;
        }}
        .metric-value.pass {{
            color: #27ae60;
        }}
        .metric-value.fail {{
            color: #e74c3c;
        }}
        .metric-value.warning {{
            color: #f39c12;
        }}
        .details {{
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #ecf0f1;
            font-size: 0.9em;
        }}
        .test-case {{
            padding: 8px;
            margin: 5px 0;
            border-left: 3px solid #3498db;
            background: #f8f9fa;
        }}
        .test-case.fail {{
            border-left-color: #e74c3c;
            background: #fee;
        }}
        .test-case.pass {{
            border-left-color: #27ae60;
            background: #efe;
        }}
        .timestamp {{
            color: #95a5a6;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <h1>System Evaluation Report</h1>
    <p class="timestamp">Generated: {datetime.now().isoformat()}</p>

    <div class="summary-card">
        <h2>Summary</h2>
        <p><strong>Total Tests:</strong> {results.get('total_tests', 0)}</p>
        <p><strong>Passed:</strong> {results.get('passed', 0)}</p>
        <p><strong>Failed:</strong> {results.get('failed', 0)}</p>
        <p><strong>Overall Score:</strong> {results.get('overall_score', 0.0):.1%}</p>
    </div>
"""

        # Add category sections
        for category, category_results in results.get("categories", {}).items():
            avg_score = category_results.get('average_score', 0)
            score_class = 'pass' if avg_score >= 0.7 else 'fail' if avg_score < 0.5 else 'warning'
            html_content += f"""
    <div class="summary-card">
        <h2>{category.replace('_', ' ').title()}</h2>
        <div class="metric-card">
            <div class="metric-header">
                <span class="metric-name">Average Score</span>
                <span class="metric-value {score_class}">
                    {avg_score:.1%}
                </span>
            </div>
            <div class="details">
                <p><strong>Tests Run:</strong> {category_results.get('tests_run', 0)}</p>
                <p><strong>Passed:</strong> {category_results.get('passed', 0)}</p>
                <p><strong>Failed:</strong> {category_results.get('failed', 0)}</p>
            </div>
        </div>
"""

            # Add test case details
            if category_results.get("test_cases"):
                html_content += "<h3>Test Cases</h3>"
                for test_case in category_results["test_cases"]:
                    status = "pass" if test_case.get("passed", False) else "fail"
                    issues_html = ""
                    if test_case.get('issues') and len(test_case.get('issues', [])) > 0:
                        issues_html = f"<p>Issues: {', '.join(test_case.get('issues', []))}</p>"
                    html_content += f"""
        <div class="test-case {status}">
            <strong>{test_case.get('name', 'Unknown')}</strong>
            <p>Score: {test_case.get('score', 0):.1%}</p>
            {issues_html}
        </div>
"""

            html_content += """
    </div>
"""

        html_content += """
</body>
</html>
"""

        with open(output_path, "w") as f:
            f.write(html_content)

        self.logger.info(f"HTML report generated: {output_path}")
        return output_path

    def generate_json_report(self, results: dict[str, Any], filename: str = "evaluation_results.json") -> Path:
        """
        Generate JSON evaluation report.

        Args:
            results: Evaluation results dictionary
            filename: Output filename

        Returns:
            Path to generated JSON file
        """
        output_path = self.output_dir / filename

        # Add metadata
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "results": results,
        }

        with open(output_path, "w") as f:
            json.dump(report_data, f, indent=2, default=str)

        self.logger.info(f"JSON report generated: {output_path}")
        return output_path
