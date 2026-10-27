import pandas as pd
from pathlib import Path
from datetime import date

# --------------------------------------------------
# 1. PROJECT SETTINGS
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TODAY = pd.Timestamp(date.today()).normalize()
RENEWAL_DAYS = 30

REQUIRED_COLUMNS = [
    "EmployeeID",
    "EmployeeName",
    "Department",
    "Operation",
    "TrainingCode",
    "TrainingName",
    "TrainingCompletionDate",
    "LicenseIssueDate",
    "LicenseExpiryDate",
    "TrainingStatus",
    "AssessmentResult",
    "TrainerAssessor",
    "ManagerApproval",
    "ManagerName",
    "ManagerApprovalDate",
    "ManagerRemarks",
]

MANDATORY_COLUMNS = [
    "EmployeeID",
    "EmployeeName",
    "Department",
    "Operation",
    "TrainingCode",
    "TrainingName",
    "TrainingCompletionDate",
    "LicenseIssueDate",
    "TrainingStatus",
    "AssessmentResult",
    "TrainerAssessor",
    "ManagerApproval",
]


# --------------------------------------------------
# 2. HELPER FUNCTIONS
# --------------------------------------------------

def clean_text(value):
    """Convert a value to trimmed text."""
    if pd.isna(value):
        return ""
    return str(value).strip()


def read_csv_file(filename):
    """Read a CSV file from the input folder."""
    path = INPUT_DIR / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Input file not found: {path}\n"
            "Check that the file exists inside the input folder."
        )

    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig"
    )


def parse_date(value):
    """Accept only YYYY-MM-DD dates; return None if invalid."""
    value = clean_text(value)

    if not value:
        return None

    try:
        parsed = pd.to_datetime(
            value,
            format="%Y-%m-%d",
            errors="raise"
        )
        return pd.Timestamp(parsed).normalize()
    except (ValueError, TypeError):
        return None


def calculate_expiry(issue_date, validity_years):
    """
    Calculate expiry as one calendar year (or configured number
    of years) after issue, minus one day.
    """
    years = int(validity_years)

    if years <= 0:
        raise ValueError("ValidityYears must be greater than zero")

    return (
        issue_date + pd.DateOffset(years=years)
        - pd.Timedelta(days=1)
    ).normalize()


def main():
    # --------------------------------------------------
    # 3. READ INPUT FILES
    # --------------------------------------------------

    employees = read_csv_file("employee_master.csv")
    training_master = read_csv_file("training_master.csv")
    records = read_csv_file("training_records.csv")

    # --------------------------------------------------
    # 4. CHECK REQUIRED COLUMNS
    # --------------------------------------------------

    required_file_columns = {
        "Employee Master": (
            employees,
            ["EmployeeID", "EmployeeName", "Department"]
        ),
        "Training Master": (
            training_master,
            ["TrainingCode", "TrainingName", "Operation",
             "ValidityYears"]
        ),
        "Training Records": (records, REQUIRED_COLUMNS),
    }

    for name, (dataframe, required) in required_file_columns.items():
        missing = set(required) - set(dataframe.columns)

        if missing:
            raise ValueError(
                f"{name} is missing columns: {sorted(missing)}"
            )

    # Standardize text in all input columns
    for dataframe in [employees, training_master, records]:
        for column in dataframe.columns:
            dataframe[column] = dataframe[column].map(clean_text)

    # Report duplicate master keys and use the first entry for lookup.
    duplicate_employee_master = employees[
        employees["EmployeeID"].duplicated(keep=False)
        & employees["EmployeeID"].ne("")
    ].copy()

    duplicate_training_master = training_master[
        training_master["TrainingCode"].duplicated(keep=False)
        & training_master["TrainingCode"].ne("")
    ].copy()

    employee_lookup = (
        employees[employees["EmployeeID"] != ""]
        .drop_duplicates("EmployeeID")
        .set_index("EmployeeID")
        .to_dict("index")
    )

    training_lookup = (
        training_master[training_master["TrainingCode"] != ""]
        .drop_duplicates("TrainingCode")
        .set_index("TrainingCode")
        .to_dict("index")
    )

    # --------------------------------------------------
    # 5. VALIDATE EACH TRAINING RECORD
    # --------------------------------------------------

    issues = []
    results = []
    seen_pairs = set()

    def add_issue(row_number, employee_id, code, issue, severity="Error"):
        issues.append({
            "SourceRow": row_number,
            "EmployeeID": employee_id,
            "TrainingCode": code,
            "Severity": severity,
            "Issue": issue,
        })

    for index, row in records.iterrows():
        row_number = index + 2  # First CSV data row is row 2
        employee_id = row["EmployeeID"]
        code = row["TrainingCode"]

        row_errors = []
        row_warnings = []

        def flag_error(message):
            if message not in row_errors:
                row_errors.append(message)
                add_issue(row_number, employee_id, code, message, "Error")

        def flag_warning(message):
            if message not in row_warnings:
                row_warnings.append(message)
                add_issue(row_number, employee_id, code, message, "Warning")

        # A. Mandatory field checks
        for column in MANDATORY_COLUMNS:
            if not row[column]:
                flag_error(f"Missing mandatory field: {column}")

        if not row["LicenseExpiryDate"]:
            flag_error("License Expiry Date is missing")

        # B. Employee Master checks
        employee = employee_lookup.get(employee_id)

        if employee_id and employee is None:
            flag_error("Employee ID not found in Employee Master")

        if employee:
            for column in ["EmployeeName", "Department"]:
                if row[column] != employee[column]:
                    flag_error(
                        f"{column} does not match Employee Master"
                    )

        # C. Training Master checks
        training = training_lookup.get(code)

        if code and training is None:
            flag_error("Training Code not found in Training Master")

        if training:
            if row["TrainingName"] != training["TrainingName"]:
                flag_error("Training Name does not match Training Master")

            if row["Operation"] != training["Operation"]:
                flag_error("Operation does not match Training Master")

        # D. Duplicate employee + training code check
        pair = (employee_id, code)

        if employee_id and code:
            if pair in seen_pairs:
                flag_error(
                    "Duplicate Employee ID + Training Code record"
                )
            else:
                seen_pairs.add(pair)

        # E. Training status and assessment
        training_status = row["TrainingStatus"].lower()
        assessment = row["AssessmentResult"].lower()

        if training_status not in [
            "completed", "in progress", "not started"
        ]:
            flag_error("Invalid Training Status")

        if assessment not in ["pass", "fail", "pending"]:
            flag_error("Invalid Assessment Result")

        if training_status != "completed":
            flag_error("Training not completed")

        if assessment != "pass":
            flag_error("Assessment not passed")

        # F. Parse and validate dates
        completion_text = row["TrainingCompletionDate"]
        issue_text = row["LicenseIssueDate"]
        expiry_text = row["LicenseExpiryDate"]

        completion = parse_date(completion_text)
        issue_date = parse_date(issue_text)
        provided_expiry = parse_date(expiry_text)

        if completion_text and completion is None:
            flag_error("Invalid Training Completion Date")

        if issue_text and issue_date is None:
            flag_error("Invalid License Issue Date")

        if expiry_text and provided_expiry is None:
            flag_error("Invalid License Expiry Date")

        if completion is None:
            flag_error("Training Completion Date is missing or invalid")
        elif completion > TODAY:
            flag_error("Training Completion Date is in the future")

        if issue_date is None:
            flag_error("License Issue Date is missing or invalid")
        elif issue_date > TODAY:
            flag_error("License Issue Date is in the future")

        if completion and issue_date:
            if issue_date < completion:
                flag_error("License issued before training completion")

        if completion and issue_date and issue_date >= completion:
            if (issue_date - completion).days > 0:
                flag_warning(
                    "License issued after training completion date"
                )

        # G. Calculate and validate license expiry
        expected_expiry = None

        if training and issue_date:
            try:
                expected_expiry = calculate_expiry(
                    issue_date,
                    training["ValidityYears"]
                )

                if (
                    provided_expiry is not None
                    and provided_expiry != expected_expiry
                ):
                    flag_error(
                        "License Expiry Date does not match policy; "
                        f"expected {expected_expiry.strftime('%Y-%m-%d')}"
                    )

            except (ValueError, TypeError, OverflowError):
                flag_error(
                    "Invalid license validity in Training Master"
                )

        # H. Manager approval validation
        approval = row["ManagerApproval"].lower()
        manager_name = row["ManagerName"]
        manager_date_text = row["ManagerApprovalDate"]
        manager_remarks = row["ManagerRemarks"]
        manager_date = None

        if approval not in ["pending", "approved", "rejected"]:
            flag_error("Invalid Manager Approval Status")

        if approval in ["approved", "rejected"]:
            if not manager_name:
                flag_error(
                    "Manager Name is required for approval/rejection"
                )

            if not manager_date_text:
                flag_error(
                    "Manager Approval Date is required for "
                    "approval/rejection"
                )
            else:
                manager_date = parse_date(manager_date_text)

                if manager_date is None:
                    flag_error("Invalid Manager Approval Date")
                elif manager_date > TODAY:
                    flag_error("Manager Approval Date is in the future")

        if approval == "rejected" and not manager_remarks:
            flag_error("Manager Remarks required for rejection")

        if approval == "pending":
            flag_warning("Manager approval is pending")

        if approval == "rejected":
            flag_error("Manager rejected this operation authorization")

        # I. Determine record status.
        # Any error means the record cannot be considered valid.
        if row_errors:
            if (
                expected_expiry is not None
                and expected_expiry < TODAY
            ):
                status = "Expired"
            else:
                status = "Invalid"
        elif expected_expiry is None:
            status = "Invalid"
            flag_error("Unable to calculate license expiry")
        elif expected_expiry < TODAY:
            status = "Expired"
            flag_error("License expired")
        elif expected_expiry <= TODAY + pd.Timedelta(
            days=RENEWAL_DAYS
        ):
            status = "Warning"
            flag_warning("License expires within 30 days")
        else:
            status = "Valid"

        # Manager approval is a separate gate from license validity.
        eligible = (
            status in ["Valid", "Warning"]
            and approval == "approved"
            and not row_errors
        )

        if status in ["Valid", "Warning"] and approval != "approved":
            eligible = False

        if approval == "pending" and not row_errors:
            status = "Pending Approval"

        # Build result record
        result = row.to_dict()
        result["CalculatedExpiryDate"] = (
            expected_expiry.strftime("%Y-%m-%d")
            if expected_expiry is not None else ""
        )
        result["ManagerApproval"] = row["ManagerApproval"]
        result["Status"] = status
        result["Eligible"] = "Yes" if eligible else "No"
        result["ValidationErrors"] = "; ".join(row_errors)
        result["Warnings"] = "; ".join(row_warnings)
        result["Issues"] = "; ".join(row_errors + row_warnings)
        results.append(result)

    # --------------------------------------------------
    # 6. BUILD REPORT DATAFRAMES
    # --------------------------------------------------

    result_df = pd.DataFrame(results)

    issue_columns = [
        "SourceRow", "EmployeeID", "TrainingCode", "Severity", "Issue"
    ]
    issues_df = pd.DataFrame(issues, columns=issue_columns)

    # Duplicate master entries are also reported.
    for _, master_row in duplicate_employee_master.iterrows():
        add_issue(
            "Employee Master",
            master_row["EmployeeID"],
            "",
            "Duplicate EmployeeID in Employee Master",
            "Error"
        )

    for _, master_row in duplicate_training_master.iterrows():
        add_issue(
            "Training Master",
            "",
            master_row["TrainingCode"],
            "Duplicate TrainingCode in Training Master",
            "Error"
        )

    # Rebuild issue report after master-level checks.
    issues_df = pd.DataFrame(issues, columns=issue_columns)

    # Records with a currently valid license and no errors.
    valid_df = result_df[result_df["Status"] == "Valid"].copy()

    # Only manager-approved, eligible records can be uploaded.
    upload_eligible_df = result_df[
        (result_df["Eligible"] == "Yes")
    ].copy()

    upload_columns = [
        "EmployeeID",
        "TrainingCode",
        "TrainingName",
        "Operation",
        "TrainingCompletionDate",
        "LicenseIssueDate",
        "CalculatedExpiryDate",
        "Status",
    ]

    upload_df = upload_eligible_df[upload_columns].rename(columns={
        "EmployeeID": "Employee ID",
        "TrainingCode": "Training Code",
        "TrainingName": "Training Name",
        "TrainingCompletionDate": "Completion Date",
        "LicenseIssueDate": "License Issue Date",
        "CalculatedExpiryDate": "License Expiry Date",
    })

    eligibility_columns = [
        "EmployeeID",
        "EmployeeName",
        "Department",
        "Operation",
        "TrainingCode",
        "Status",
        "ManagerApproval",
        "ManagerName",
        "ManagerApprovalDate",
        "ManagerRemarks",
        "Eligible",
        "Issues",
    ]
    eligibility_df = result_df[eligibility_columns].copy()

    manager_report = result_df[
        [
            "EmployeeID",
            "EmployeeName",
            "Operation",
            "TrainingCode",
            "Status",
            "ManagerApproval",
            "ManagerName",
            "ManagerApprovalDate",
            "ManagerRemarks",
            "Eligible",
        ]
    ].copy()

    # --------------------------------------------------
    # 7. SAVE CSV REPORTS
    # --------------------------------------------------

    result_df.to_csv(
        OUTPUT_DIR / "employee_license_status.csv",
        index=False,
        encoding="utf-8-sig"
    )
    issues_df.to_csv(
        OUTPUT_DIR / "validation_issues.csv",
        index=False,
        encoding="utf-8-sig"
    )
    valid_df.to_csv(
        OUTPUT_DIR / "valid_records.csv",
        index=False,
        encoding="utf-8-sig"
    )
    eligibility_df.to_csv(
        OUTPUT_DIR / "operation_eligibility.csv",
        index=False,
        encoding="utf-8-sig"
    )
    manager_report.to_csv(
        OUTPUT_DIR / "manager_approval_report.csv",
        index=False,
        encoding="utf-8-sig"
    )
    upload_df.to_csv(
        OUTPUT_DIR / "upload_ready.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Excel upload file
    upload_df.to_excel(
        OUTPUT_DIR / "upload_ready.xlsx",
        index=False
    )

    # Combined workbook for HR review
    with pd.ExcelWriter(
        OUTPUT_DIR / "management_reports.xlsx",
        engine="openpyxl"
    ) as writer:
        result_df.to_excel(
            writer, sheet_name="License Status", index=False
        )
        issues_df.to_excel(
            writer, sheet_name="Validation Issues", index=False
        )
        eligibility_df.to_excel(
            writer, sheet_name="Operation Eligibility", index=False
        )
        manager_report.to_excel(
            writer, sheet_name="Manager Approval", index=False
        )
        upload_df.to_excel(
            writer, sheet_name="Upload Ready", index=False
        )

    # --------------------------------------------------
    # 8. MANAGEMENT SUMMARY
    # --------------------------------------------------

    status_counts = result_df["Status"].value_counts()

    incomplete_count = (
        result_df["TrainingStatus"].str.lower() != "completed"
    ).sum()
    failed_count = (
        result_df["AssessmentResult"].str.lower() == "fail"
    ).sum()
    duplicate_count = issues_df["Issue"].str.contains(
        "Duplicate", case=False, na=False
    ).sum()
    missing_invalid_count = issues_df["Issue"].str.contains(
        "Missing|Invalid", case=False, regex=True, na=False
    ).sum()

    summary = [
        "TRAINING & EMPLOYEE LICENSE VALIDATOR",
        f"Report date: {TODAY.date()}",
        f"Employees in Employee Master: {len(employees)}",
        f"Training records processed: {len(result_df)}",
        f"Valid licenses: {int((result_df['Status'] == 'Valid').sum())}",
        f"Expired licenses: {int((result_df['Status'] == 'Expired').sum())}",
        f"Licenses expiring within 30 days: {int((result_df['Status'] == 'Warning').sum())}",
        f"Pending manager approval: {int((result_df['ManagerApproval'].str.lower() == 'pending').sum())}",
        f"Manager-rejected records: {int((result_df['ManagerApproval'].str.lower() == 'rejected').sum())}",
        f"Invalid records: {int((result_df['Status'] == 'Invalid').sum())}",
        f"Incomplete training records: {int(incomplete_count)}",
        f"Failed assessment records: {int(failed_count)}",
        f"Duplicate issues reported: {int(duplicate_count)}",
        f"Missing/invalid data issues: {int(missing_invalid_count)}",
        f"Eligible records: {int((result_df['Eligible'] == 'Yes').sum())}",
        f"Employees with at least one eligible operation: {result_df.loc[result_df['Eligible'] == 'Yes', 'EmployeeID'].nunique()}",
        f"Employees with no eligible records: {result_df.loc[result_df['Eligible'] == 'No', 'EmployeeID'].nunique()}",
        f"Upload-ready records: {len(upload_df)}",
        "",
        "Review validation_issues.csv and manager_approval_report.csv.",
        "Only eligible, manager-approved records are included in upload_ready.csv/xlsx.",
    ]

    (OUTPUT_DIR / "summary_report.txt").write_text(
        "\n".join(summary),
        encoding="utf-8"
    )

    # --------------------------------------------------
    # 9. FINISH
    # --------------------------------------------------

    print("\nValidation completed.")
    print("\n".join(summary))
    print(f"\nReports saved in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
