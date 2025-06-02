#!/usr/bin/env python3
import hashlib
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import sys

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

FIXED_MANIFEST_FILENAME = "fitgirl-bins.md5"

def calculate_md5_for_file(filepath, block_size=65536):
    """Calculates the MD5 hash of a file."""
    md5 = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while True:
                data = f.read(block_size)
                if not data:
                    break
                md5.update(data)
        return md5.hexdigest()
    except FileNotFoundError:
        return None
    except IOError as e:
        print(f"IOError reading {filepath}: {e}")
        return "IO_ERROR"

def process_file_entry(filepath_to_check, expected_md5, manifest_file_path_for_logging):
    """
    Worker function to check a single file.
    Returns a tuple: (status_code, message, calculated_hash_or_None)
    status_code: "OK", "FAILED", "MISSING", "ERROR"
    """
    if not os.path.exists(filepath_to_check):
        return "MISSING", f"MISSING: {os.path.relpath(filepath_to_check, os.path.dirname(manifest_file_path_for_logging))}", None

    actual_md5 = calculate_md5_for_file(filepath_to_check)

    relative_path_for_display = os.path.relpath(filepath_to_check, os.path.dirname(manifest_file_path_for_logging))

    if actual_md5 is None: # Should have been caught by os.path.exists, but defensive
        return "MISSING", f"MISSING: {relative_path_for_display} (could not open after initial check)", None
    if actual_md5 == "IO_ERROR":
        return "ERROR", f"ERROR reading: {relative_path_for_display}", None

    if actual_md5.lower() == expected_md5.lower():
        return "OK", f"OK: {relative_path_for_display}", actual_md5
    else:
        return "FAILED", f"FAILED: {relative_path_for_display}\n  Expected: {expected_md5}\n  Actual:   {actual_md5}", actual_md5

def main():
    parser = argparse.ArgumentParser(description=f"Multithreaded MD5 file checker. Expects '{FIXED_MANIFEST_FILENAME}' in its own directory.")
    parser.add_argument(
        "-t", "--threads",
        type=int,
        default=os.cpu_count() or 1,
        help="Number of worker threads to use."
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    manifest_file_path = os.path.join(script_dir, FIXED_MANIFEST_FILENAME)

    if not os.path.isfile(manifest_file_path):
        print(f"Error: Manifest file '{FIXED_MANIFEST_FILENAME}' not found in the script's directory:")
        print(f"       {script_dir}")
        print(f"Please ensure '{FIXED_MANIFEST_FILENAME}' is present alongside the script.")
        sys.exit(1)

    tasks = []
    manifest_dir = script_dir

    print(f"Using manifest file: {manifest_file_path}")
    print(f"Base directory for files (relative to manifest): {manifest_dir}")
    print(f"Using {args.threads} worker threads.\n")

    try:
        with open(manifest_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith(';'):
                    continue

                parts = line.split('*', 1)
                if len(parts) != 2:
                    print(f"Warning: Skipping malformed line {line_num} in manifest: {line}")
                    continue

                expected_hash = parts[0].strip()
                relative_path_from_manifest_entry = parts[1].strip()

                absolute_file_path_to_check = os.path.abspath(os.path.join(manifest_dir, relative_path_from_manifest_entry))
                tasks.append((absolute_file_path_to_check, expected_hash, manifest_file_path))

    except Exception as e:
        print(f"Error reading manifest file {manifest_file_path}: {e}")
        sys.exit(1)

    if not tasks:
        print(f"No files to check found in {FIXED_MANIFEST_FILENAME}.")
        return

    results_ok = []
    results_failed = []
    results_missing = []
    results_error = []

    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        future_to_task = {
            executor.submit(process_file_entry, task_path, task_hash, manifest_path_log): (task_path, task_hash)
            for task_path, task_hash, manifest_path_log in tasks
        }

        iterable_futures = as_completed(future_to_task)
        if TQDM_AVAILABLE:
            iterable_futures = tqdm(iterable_futures, total=len(tasks), desc="Checking files", unit="file")

        for future in iterable_futures:
            original_filepath, original_hash = future_to_task[future]
            try:
                status, message, _ = future.result()
                if status == "OK":
                    results_ok.append(message)
                    if not TQDM_AVAILABLE: print(message)
                elif status == "FAILED":
                    results_failed.append(message)
                    print(message)
                elif status == "MISSING":
                    results_missing.append(message)
                    print(message)
                elif status == "ERROR":
                    results_error.append(message)
                    print(message)

            except Exception as exc:
                err_msg = f"ERROR processing {os.path.relpath(original_filepath, manifest_dir)}: {exc}"
                results_error.append(err_msg)
                print(err_msg)

    end_time = time.perf_counter()
    total_time = end_time - start_time

    print("\n--- Verification Summary ---")
    if TQDM_AVAILABLE and results_ok:
        for ok_msg in results_ok:
            print(ok_msg)

    if results_failed:
        print(f"\n--- {len(results_failed)} FAILED CHECKS ---")
        for fail_msg in results_failed:
            print(fail_msg)
    if results_missing:
        print(f"\n--- {len(results_missing)} MISSING FILES ---")
        for miss_msg in results_missing:
            print(miss_msg)
    if results_error:
        print(f"\n--- {len(results_error)} ERRORS DURING PROCESSING ---")
        for err_msg in results_error:
            print(err_msg)

    print(f"\nChecked {len(tasks)} files from {FIXED_MANIFEST_FILENAME}.")
    print(f"  OK:      {len(results_ok)}")
    print(f"  Failed:  {len(results_failed)}")
    print(f"  Missing: {len(results_missing)}")
    print(f"  Errors:  {len(results_error)}")
    print(f"Total time: {total_time:.2f} seconds.")

    if not results_failed and not results_missing and not results_error:
        print("\nAll files verified successfully!")
    else:
        print("\nVerification complete. Some issues were found.")
        sys.exit(1)

if __name__ == "__main__":
    main()
