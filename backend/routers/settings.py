from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db, UserSettings
from schemas import SettingsUpdate, SettingsResponse

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    s = db.query(UserSettings).first()
    if not s:
        s = UserSettings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.patch("", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    s = db.query(UserSettings).first()
    if not s:
        s = UserSettings(id=1)
        db.add(s)

    for field, val in body.model_dump(exclude_none=True).items():
        setattr(s, field, val)

    db.commit()
    db.refresh(s)
    return s
