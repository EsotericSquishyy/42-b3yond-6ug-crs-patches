#!/usr/bin/env python3
import sys
import re
from parser.unifiedparser import UnifiedSanitizerReport
from parser.jazzer import JazzerSanitizerReport

def main():
    if len(sys.argv) != 3:
        print("Usage: python test_parser.py <path_to_crash_report> <sanitizer>")
        sys.exit(1)

    crash_report_path = sys.argv[1]
    sanitizer = sys.argv[2]

    # Read the crash report file from the given path
    try:
        with open(crash_report_path, "r") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file '{crash_report_path}': {e}")
        sys.exit(1)

    if sanitizer == "JAZZER":
        parser = JazzerSanitizerReport
    else:
        parser = UnifiedSanitizerReport

    # Parse the crash report using the specified sanitizer
    report = parser.parse(content)

    if report is None:
        print("No sanitizer report could be parsed from the crash report.")
    else:
        try:
            if isinstance(report, UnifiedSanitizerReport) or isinstance(report, JazzerSanitizerReport):
                print("Parsed Sanitizer Report:")
                print("=" * 50)
                # Print the summary (which includes the vulnerability explanation,
                # the original report content, and repair advice)
                # print("Summary:")
                # print(report.summary)
                print("\nDetails:")
                print(f"Sanitizer: {report.sanitizer}")
                print(f"CWE: {report.cwe}")
                print(f"Trigger point: {report.trigger_point}")
                print(f"Summary:\n{report.summary}")
                print("=" * 50)
            else:
                print("Parsed Sanitizer Report:")
                print(report)
        except ImportError:
            print("Parsed Sanitizer Report:")
            print(report)

if __name__ == "__main__":
    main()