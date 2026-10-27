
import pandas as pd
from pathlib import Path
from datetime import date

# Project folders
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

OUTPUT_DIR.mkdir(exist_ok=True)

TODAY = pd.Timestamp(date.today()).normalize()
RENEWAL_DAYS = 30

REQUIRED_COLUMNS = [
    "EmployeeID", "EmployeeName", "Department", "Operation",
    "TrainingCode", "TrainingName", "TrainingCompletionDate",
    "LicenseIssueDate", "LicenseExpiryDate", "TrainingStatus",
    "AssessmentResult", "TrainerAssessor"
]

MANDATORY_COLUMNS = [
    "EmployeeID", "EmployeeName", "Department", "Operation",
    "TrainingCode", "TrainingName", "TrainingCompletionDate",
    "LicenseIssueDate", "TrainingStatus", "AssessmentResult",
    "TrainerAssessor"
]


def clean_text(value):
    """Remove unnecessary spaces and standardize text."""
    return str(value).strip()


def read_csv_file(filename):
    """Read a CSV file and treat blank values consistently."""
    path = INPUT_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    return pd.read_csv(path, dtype=str, keep_default_na=False)


def parse_date(value):
    """Return a valid date or None."""
    value = clean_text(value)

    if not value:
        return None

    try:
        parsed = pd.to_datetime(
            value, format="%Y-%m-%d", errors="raise"
        )
        return parsed.normalize()
    except (ValueError, TypeError):
        return None


def main():
    # 1. Read the three input files
    employees = read_csv_file("employee_master.csv")
    training_master = read_csv_file("training_master.csv")
    records = read_csv_file("training_records.csv")

    # 2. Check required columns
    for name, dataframe, required in [
        ("Employee Master", employees,
         ["EmployeeID", "EmployeeName", "Department"]),
        ("Training Master", training_master,
         ["TrainingCode", "TrainingName", "Operation",
          "ValidityYears"]),
        ("Training Records", records, REQUIRED_COLUMNS)
    ]:
        missing = set(required) - set(dataframe.columns)
        if missing:
            raise ValueError(
                f"{name} is missing columns: {sorted(missing)}"
            )

    # 3. Standardize text
    for dataframe in [employees, training_master, records]:
        for column in dataframe.columns:
            dataframe[column] = dataframe[column].map(clean_text)

    # 4. Prepare master lookups
    employee_lookup = employees.drop_duplicates(
        "EmployeeID"
    ).set_index("EmployeeID").to_dict("index")

    training_lookup = training_master.drop_duplicates(
        "TrainingCode"
    ).set_index("TrainingCode").to_dict("index")

    issues = []
    results = []
    seen = set()

    def add_issue(row_number, employee_id, code, issue):
        issues.append({
            "SourceRow": row_number,
            "EmployeeID": employee_id,
            "TrainingCode": code,
            "Issue": issue
        })

    # 5. Validate every training record
    for index, row in records.iterrows():
        row_number = index + 2  # CSV header is row 1
        employee_id = row["EmployeeID"]
        code = row["TrainingCode"]
        row_issues = []

        def flag(message):
            row_issues.append(message)
            add_issue(row_number, employee_id, code, message)

        # Mandatory fields
        for column in MANDATORY_COLUMNS:
            if not row[column]:
                flag(f"Missing mandatory field: {column}")

        # Employee Master validation
        employee = employee_lookup.get(employee_id)

        if employee_id and employee is None:
            flag("Employee ID not found in Employee Master")

        if employee:
            for column in ["EmployeeName", "Department"]:
                if row[column] != employee[column]:
                    flag(f"{column} does not match Employee Master")

        # Training Master validation
        training = training_lookup.get(code)

        if code and training is None:
            flag("Training Code not found in Training Master")

        if training:
            if row["TrainingName"] != training["TrainingName"]:
                flag("Training Name does not match Training Master")

            if row["Operation"] != training["Operation"]:
                flag("Operation does not match Training Master")

        # Duplicate employee + training records
        duplicate_key = (employee_id, code)

        if employee_id and code:
            if duplicate_key in seen:
                flag("Duplicate Employee ID + Training Code record")
            else:
                seen.add(duplicate_key)

        # Training status and assessment
        training_status = row["TrainingStatus"].lower()
        assessment = row["AssessmentResult"].lower()

        if training_status not in [
            "completed", "in progress", "not started"
        ]:
            flag("Invalid Training Status")

        if assessment not in ["pass", "fail", "pending"]:
            flag("Invalid Assessment Result")

        if training_status != "completed":
            flag("Training not completed")

        if assessment != "pass":
            flag("Assessment not passed")

        # Parse dates
        completion = parse_date(row["TrainingCompletionDate"])
        issue_date = parse_date(row["LicenseIssueDate"])
        provided_expiry = parse_date(row["LicenseExpiryDate"])

        if row["TrainingCompletionDate"] and completion is None:
            flag("Invalid Training Completion Date")

        if row["LicenseIssueDate"] and issue_date is None:
            flag("Invalid License Issue Date")

        if row["LicenseExpiryDate"] and provided_expiry is None:
            flag("Invalid License Expiry Date")

        if completion is None:
            flag("Training Completion Date is missing or invalid")
        elif completion > TODAY:
            flag("Training Completion Date is in the future")

        if issue_date is None:
            flag("License Issue Date is missing or invalid")
        elif issue_date > TODAY:
            flag("License Issue Date is in the future")

        if completion and issue_date and issue_date < completion:
            flag("License issued before training completion")

        # Calculate expected license expiry
        expected_expiry = None

        if training and issue_date:
            try:
                years = int(training["ValidityYears"])

                if years <= 0:
                    raise ValueError("Validity must be positive")

                expected_expiry = (
                    issue_date + pd.DateOffset(years=years)
                    - pd.Timedelta(days=1)
                ).normalize()

                if (
                    provided_expiry is not None
                    and provided_expiry != expected_expiry
                ):
                    flag("License Expiry Date does not match policy")

            except (ValueError, TypeError):
                flag("Invalid license validity in Training Master")

        elif provided_expiry is None:
            # Missing/invalid expiry is already reported above.
            pass

        # Determine license status
        if not row_issues:
            if expected_expiry < TODAY:
                status = "Expired"
                flag("License expired")
            elif expected_expiry <= TODAY + pd.Timedelta(
                days=RENEWAL_DAYS
            ):
                status = "Warning"
                flag("License expires within 30 days")
            else:
                status = "Valid"
        else:
            status = "Invalid"

        eligible = status in ["Valid", "Warning"] and not row_issues

        # A renewal warning is reportable but need not revoke eligibility.
        if status == "Warning":
            eligible = True

        # Save result
        result = row.to_dict()
        result["CalculatedExpiryDate"] = (
            expected_expiry.strftime("%Y-%m-%d")
            if expected_expiry is not None else ""
        )
        result["Status"] = status
        result["Eligible"] = "Yes" if eligible else "No"
        result["Issues"] = "; ".join(row_issues) if row_issues else ""
        results.append(result)

    # 6. Build reports
    result_df = pd.DataFrame(results)
    issues_df = pd.DataFrame(
        issues, columns=["SourceRow", "EmployeeID",
                         "TrainingCode", "Issue"]
    )

    # Records with no issues are valid and upload-ready
    valid_df = result_df[result_df["Status"] == "Valid"].copy()

    upload_columns = [
        "EmployeeID", "TrainingCode", "TrainingName", "Operation",
        "TrainingCompletionDate", "LicenseIssueDate",
        "CalculatedExpiryDate", "Status"
    ]

    upload_df = valid_df[upload_columns].rename(columns={
        "EmployeeID": "Employee ID",
        "TrainingCode": "Training Code",
        "TrainingName": "Training Name",
        "TrainingCompletionDate": "Completion Date",
        "LicenseIssueDate": "License Issue Date",
        "CalculatedExpiryDate": "License Expiry Date"
    })

    # Employee-operation eligibility report
    eligibility_df = result_df[
        ["EmployeeID", "EmployeeName", "Department",
         "Operation", "TrainingCode", "Status", "Eligible", "Issues"]
    ].copy()

    # 7. Save CSV reports
    result_df.to_csv(
        OUTPUT_DIR / "employee_license_status.csv", index=False
    )
    issues_df.to_csv(
        OUTPUT_DIR / "validation_issues.csv", index=False
    )
    valid_df.to_csv(
        OUTPUT_DIR / "valid_records.csv", index=False
    )
    eligibility_df.to_csv(
        OUTPUT_DIR / "operation_eligibility.csv", index=False
    )
    upload_df.to_csv(
        OUTPUT_DIR / "upload_ready.csv", index=False
    )

    # 8. Save upload-ready Excel
    upload_df.to_excel(
        OUTPUT_DIR / "upload_ready.xlsx", index=False
    )

    # 9. Generate management summary
    summary = [
        "TRAINING & EMPLOYEE LICENSE VALIDATOR",
        f"Report date: {TODAY.date()}",
        f"Total employees in master: {len(employees)}",
        f"Training records processed: {len(result_df)}",
        f"Valid licenses: {(result_df['Status'] == 'Valid').sum()}",
        f"Expired licenses: {(result_df['Status'] == 'Expired').sum()}",
        f"Licenses expiring soon: {(result_df['Status'] == 'Warning').sum()}",
        f"Invalid records: {(result_df['Status'] == 'Invalid').sum()}",
        f"Records with issues: {len(issues_df)}",
        f"Duplicate records: {issues_df['Issue'].str.contains('Duplicate', case=False).sum()}",
        f"Upload-ready records: {len(upload_df)}",
        "",
        "Review validation_issues.csv before correcting source data."
    ]

    (OUTPUT_DIR / "summary_report.txt").write_text(
        "\n".join(summary), encoding="utf-8"
    )

    print("\nValidation completed successfully!")
    print("\n".join(summary))
    print(f"\nReports saved in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
