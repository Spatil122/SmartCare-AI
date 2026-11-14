"""
SMARTCARE AI - Complete Streamlit application
Includes patient complaints, Ollama AI assistance, hospital dashboards,
hospital registration, and doctor / medical-service availability.

Beginner note:
- This app uses the existing smartcare.db database.
- New tables and columns are added safely; existing complaint records are kept.
- Ollama is optional. If it is unavailable, complaint registration still works.
"""

import os
import json
import uuid
import random
import hashlib
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta

import streamlit as st
import plotly.express as px


# ---------------------------------------------------------
# PAGE SETTINGS
# ---------------------------------------------------------

st.set_page_config(
    page_title="SMARTCARE AI",
    page_icon="🏥",
    layout="wide"
)

DB_PATH = "smartcare.db"

DEFAULT_MEDICAL_CATEGORIES = [
    "Dental",
    "Bone / Orthopaedics",
    "X-ray / Radiology",
    "General Medicine",
    "Cardiology",
    "Eye Care",
    "ENT",
    "Gynaecology",
    "Paediatrics",
]

COMPLAINT_CATEGORIES = {
    "English": [
        "Doctor Unavailable",
        "Medicine Unavailable",
        "Cleanliness Problem",
        "Water Problem",
        "Bed Unavailable",
        "Hospital Facilities Problem",
        "Staff Behaviour Problem",
        "Other",
    ],
    "Kannada": [
        "ವೈದ್ಯರು ಲಭ್ಯವಿಲ್ಲ",
        "ಔಷಧಿ ಲಭ್ಯವಿಲ್ಲ",
        "ಸ್ವಚ್ಛತೆ ಸಮಸ್ಯೆ",
        "ನೀರಿನ ಸಮಸ್ಯೆ",
        "ಹಾಸಿಗೆ ಲಭ್ಯವಿಲ್ಲ",
        "ಆಸ್ಪತ್ರೆ ಸೌಲಭ್ಯ ಸಮಸ್ಯೆ",
        "ಸಿಬ್ಬಂದಿ ವರ್ತನೆ ಸಮಸ್ಯೆ",
        "ಇತರೆ",
    ],
    "Hindi": [
        "डॉक्टर उपलब्ध नहीं",
        "दवाइयां उपलब्ध नहीं",
        "सफाई की समस्या",
        "पानी की समस्या",
        "बेड उपलब्ध नहीं",
        "अस्पताल की सुविधाओं की समस्या",
        "कर्मचारियों के व्यवहार की समस्या",
        "अन्य",
    ],
}


# ---------------------------------------------------------
# DATABASE CONNECTION AND SAFE MIGRATIONS
# ---------------------------------------------------------

def get_connection():
    """Open the SQLite database and ensure required tables exist."""
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def column_exists(connection, table_name, column_name):
    """Check whether a database column already exists."""
