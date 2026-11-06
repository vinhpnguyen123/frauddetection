"""Celery application. Ingestion tasks arrive in M2-S5."""

from celery import Celery

from app.config import get_settings

celery_app = Celery("frauddetection", broker=get_settings().redis_url)
