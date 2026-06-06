"""Interactive NoteVision OMR application."""

import streamlit as st


def main() -> None:
    """Render the application."""
    st.title("notevision-omr")
    st.write("Система анализа сканированных нотных документов.")


if __name__ == "__main__":
    main()
