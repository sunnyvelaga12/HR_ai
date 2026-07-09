"""
End-to-end smoke test for all new HR endpoints.
Run: python test_hr_flow.py
Backend must be running on port 8000.
"""
import httpx
import asyncio
import io
import csv

BASE = "http://localhost:8000"

async def run():
    async with httpx.AsyncClient(timeout=20.0) as c:
        print("=" * 50)
        print("1. Signup HR Admin")
        r = await c.post(f"{BASE}/api/auth/signup", json={
            "email": "hrtest@wizard.com",
            "password": "hrtest123",
            "role": "hr_admin",
            "companyName": "Wizard Corp"
        })
        print(f"   {r.status_code} — {r.text[:80]}")

        print("\n2. Login")
        r = await c.post(f"{BASE}/api/auth/login", json={
            "email": "hrtest@wizard.com",
            "password": "hrtest123"
        })
        assert r.status_code == 200, f"Login failed: {r.text}"
        data = r.json()
        token = data["accessToken"]
        company_id = data["companyId"]
        print(f"   200 — companyId={company_id[:8]}…")

        headers = {"Authorization": f"Bearer {token}"}

        print("\n3. Create Company (form + no logo)")
        r = await c.post(
            f"{BASE}/api/hr/companies",
            data={"companyName": "Wizard Corp Updated"},
            headers=headers,
        )
        print(f"   {r.status_code} — {r.text[:80]}")
        assert r.status_code == 201, r.text

        print("\n4. Upload TXT policy document")
        txt_content = b"Section 1: Leave Policy\nAll employees get 20 days annual leave.\n\nSection 2: WFH\nUp to 3 days WFH per week is allowed."
        r = await c.post(
            f"{BASE}/api/hr/companies/{company_id}/documents",
            files={"file": ("policy.txt", io.BytesIO(txt_content), "text/plain")},
            headers=headers,
        )
        print(f"   {r.status_code} — {r.text[:120]}")
        assert r.status_code == 201, r.text
        doc = r.json()
        doc_id = doc["id"]
        assert doc["status"] == "ready"
        print(f"   doc_id={doc_id[:8]}… status={doc['status']}")

        print("\n5. List documents")
        r = await c.get(f"{BASE}/api/hr/companies/{company_id}/documents", headers=headers)
        print(f"   {r.status_code} — {len(r.json()['documents'])} docs")

        print("\n6. Preview CSV employees")
        csv_content = "Full Name,Email,Role,Department\nAlice Smith,alice@test.com,Engineer,Engineering\nBob Jones,bob@test.com,Designer,Product\nCarol White,carol@test.com,Manager,HR\nDave Brown,dave@test.com,Analyst,Finance"
        r = await c.post(
            f"{BASE}/api/hr/companies/{company_id}/employees/preview",
            files={"file": ("employees.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=headers,
        )
        print(f"   {r.status_code}")
        assert r.status_code == 200, r.text
        preview = r.json()
        print(f"   total_rows={preview['total_rows']}, preview={len(preview['rows'])} rows")
        for row in preview["rows"]:
            print(f"     · {row['fullName']} | {row['email']} | {row['role']} | {row['department']}")

        print("\n7. Import employees")
        r = await c.post(
            f"{BASE}/api/hr/companies/{company_id}/employees/import?sendInvites=false",
            files={"file": ("employees.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=headers,
        )
        print(f"   {r.status_code} — {r.text[:120]}")
        assert r.status_code == 201, r.text
        result = r.json()
        print(f"   created={result['created']} updated={result['updated']} skipped={result['skipped']}")

        print("\n8. Delete document")
        r = await c.delete(f"{BASE}/api/hr/companies/{company_id}/documents/{doc_id}", headers=headers)
        print(f"   {r.status_code} — {r.text}")

        print("\n9. Policy text for chat (via company_policies)")
        # Re-upload to test chat path
        r = await c.post(
            f"{BASE}/api/hr/companies/{company_id}/documents",
            files={"file": ("policy2.txt", io.BytesIO(txt_content), "text/plain")},
            headers=headers,
        )
        print(f"   Re-upload: {r.status_code}")

        print("\n" + "=" * 50)
        print("✅ All tests passed!")

asyncio.run(run())
