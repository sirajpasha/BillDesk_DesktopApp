# Rebuilding the user guide and the in-program help

The text lives in **one** file: `Docs/BillDesk_Native_User_Guide.src.md`. Everything else is generated.

1. **Screenshots** (only when a screen changed). Start a throw-away MongoDB and point the app at a database whose name contains `demo` **and** `qa` (the scripts refuse anything else):
   `MONGODB_URL=mongodb://127.0.0.1:27099  DB_NAME=sv_billing_qa_demo  QA_SCRATCH=<scratch dir>  PYTHONPATH=tests/qa_realdb:.`
   - `python scripts/seed_database.py`, then `python scripts/user_guide/demo_data.py` and `python scripts/user_guide/demo_extra.py` (fictional customers, items, bills, orders, purchases, returns).
   - `python scripts/user_guide/capture_screenshots.py` drives the real app and writes the PNGs to `$QA_SCRATCH/guide_img` (and a dump of every button / list it saw to `ui_dump.txt`); copy them to `Docs/user-guide-native/img/`.
   - After the first build, `python scripts/user_guide/capture_help.py` photographs the Help screen itself (`120-`, `121-`); copy those too.
2. **Text**: edit `Docs/BillDesk_Native_User_Guide.src.md`. Each topic is a `###` heading followed by `<!-- id: ... | screen: ... | keywords: ... | related: ... | context: Page; Page -->`. Link topics with `[text](#topic-id)`. Keywords and the "I want to..." table are what the Help search uses; add the words people would type.
3. **Build**: `python scripts/build_user_guide.py` -> `Docs/BillDesk_Native_User_Guide.md / .docx / .pdf / .ipynb` and `app/assets/help/guide.json` + `img/` (the Help screen). It stops with a list of problems if an id, a link or an image is missing.
4. `python -m pytest tests/test_help.py` checks the guide, the search and the Help screen.
