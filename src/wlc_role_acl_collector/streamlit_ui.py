"""Widgets shared by the local Web app and the public demo."""

from pathlib import Path

import streamlit as st
from packaging.version import Version


def render_role_network_sample_download(config_dir: Path) -> None:
    sample = config_dir / "role_networks.example.xlsx"
    try:
        data = sample.read_bytes()
    except OSError:
        st.warning("사내 Role 대역표 샘플 파일을 열 수 없습니다.")
        return

    st.download_button(
        "사내 Role 대역표 샘플 다운로드 (.xlsx)",
        data=data,
        file_name=sample.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        on_click="ignore" if Version(st.__version__) >= Version("1.43") else None,
    )
