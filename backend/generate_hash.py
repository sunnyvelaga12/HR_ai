#!/usr/bin/env python3
"""
generate_hash.py — Secure bcrypt hash generator for the super-admin password.

Usage:
    cd backend
    python generate_hash.py

This script will:
  1. Prompt you to enter your desired admin password (input is hidden)
  2. Confirm the password
  3. Generate a bcrypt hash (cost factor 12)
  4. Print the hash so you can paste it into backend/.env as ADMIN_PASSWORD_HASH

The plaintext password is NEVER written to any file or log.
"""

import getpass
import sys


def main():
    print("=" * 60)
    print("  SentiNews Admin Password Hash Generator")
    print("=" * 60)
    print()
    print("Enter the password you want to use for the super-admin account.")
    print("Password requirements:")
    print("  ✓ At least 8 characters")
    print("  ✓ At least one uppercase letter")
    print("  ✓ At least one digit (0-9)")
    print("  ✓ At least one special character (!@#$%^&* etc.)")
    print()

    try:
        import bcrypt
    except ImportError:
        print("ERROR: bcrypt is not installed.")
        print("Run: pip install passlib[bcrypt]")
        sys.exit(1)

    import re

    while True:
        password = getpass.getpass("Enter admin password: ")

        # Validate strength
        errors = []
        if len(password) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", password):
            errors.append("at least one uppercase letter")
        if not re.search(r"[0-9]", password):
            errors.append("at least one digit")
        if not re.search(r"[^a-zA-Z0-9]", password):
            errors.append("at least one special character")

        if errors:
            print(f"\n⚠  Weak password — must have: {', '.join(errors)}")
            print("Please try again.\n")
            continue

        confirm = getpass.getpass("Confirm admin password: ")
        if password != confirm:
            print("\n⚠  Passwords do not match. Please try again.\n")
            continue

        break

    # Generate hash (bcrypt cost factor 12)
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    print()
    print("=" * 60)
    print("  ✅ Hash generated successfully!")
    print("=" * 60)
    print()
    print("Copy the lines below and paste them into  backend/.env :")
    print()
    print(f"ADMIN_EMAIL=your-email@example.com")
    print(f"ADMIN_PASSWORD_HASH={hashed}")
    print()
    print("Replace 'your-email@example.com' with your actual admin email.")
    print("IMPORTANT: Never commit .env to version control!")
    print()


if __name__ == "__main__":
    main()
