# Training & Employee License Validator

## 1. Project Overview

The Training & Employee License Validator is a Python-based application that validates employee training and operation-license records for a manufacturing organization. It helps HR/L&D identify incomplete training, failed assessments, expired licenses, upcoming renewals, duplicate records, and invalid data.

## 2. Technologies Used

- Python
- Pandas
- CSV files
- Excel (.xlsx)
- openpyxl
- Git and GitHub

## 3. Project Structure

```text
Training & Employee License Validator/
├── input/
│   ├── employee_master.csv
│   ├── training_master.csv
│   └── training_records.csv
├── output/
├── main.py
├── business_rules.txt
└── README.md
```

## 4. Business Rules

- Employee ID must exist in Employee Master.
- Training Code, Training Name, and Operation must match Training Master.
- Training must be completed and assessment must be passed.
- Dates must be valid and completion/issue dates cannot be in the future.
- License expiry must follow the configured validity policy.
- Expired licenses, renewal warnings, duplicates, and missing data must be identified.
- Only records meeting all required upload criteria are included in the upload file.

## 5. Installation

Install Python 3 and run:

```bash
python -m pip install pandas openpyxl
```

## 6. How to Run

Place the three input CSV files in the `input` directory.

Run:

```bash
python main.py
```

The generated reports will be saved in the `output` directory.

## 7. Input Files

- `employee_master.csv`: Employee details.
- `training_master.csv`: Approved training codes, operation mappings, and license validity.
- `training_records.csv`: Employee training and license records to validate.

## 8. Output Files

- `employee_license_status.csv`: License status for all records.
- `validation_issues.csv`: Errors and warnings.
- `valid_records.csv`: Records with valid licenses.
- `operation_eligibility.csv`: Employee eligibility by operation.
- `upload_ready.csv`: Clean upload-ready data.
- `upload_ready.xlsx`: Excel version of the upload-ready data.
- `summary_report.txt`: Management summary.

## 9. Validation Logic

The application reads the input CSV files, standardizes text, looks up employee and training masters, checks mandatory fields, detects duplicates, validates dates and assessment status, calculates license expiry, and categorizes records. It then exports validation results and management reports.

## 10. Assumptions and Limitations

The sample solution assumes a one-year license validity period and uses an expiry date one day before the anniversary of issue. This must be confirmed with the organization's policy. The solution uses sample data and local files; integration with a production LMS/HRMS is not included.

The upload file must be reviewed and tested against the target platform's schema before actual use.

