- [ ] Update `backend/app/db.py` to build Mongo URI from MONGO_USER/MONGO_PASSWORD/MONGO_HOST/MONGO_DB with quote_plus
- [ ] Add startup validation with clear error listing missing env vars
- [ ] Update `backend/app/config.py` to introduce new env vars and (optionally) keep MONGODB_URI fallback
- [ ] Search repo for other `MONGODB_URI` usages and update consistently (note: ripgrep may be missing)
- [x] Update `.env` / `.env.example` variable names (manual if tool cannot edit/read)
- [ ] Run backend startup and tests (`test_mongo.py`, `test_signup.py`) to verify


