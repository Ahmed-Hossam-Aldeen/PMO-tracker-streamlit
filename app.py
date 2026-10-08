import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

EXAMPLE = """14/9/2026
16/9/2026
19/9/2026
26/9/2026
30/9/2026
1/10/2026
3/10/2026
7/10/2026"""
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_dates(text):
    """Accept one date per line plus an optional header; never skip bad lines."""
    dates, errors = [], []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.lower().rstrip(":").strip() == "failed on":
            continue
        if not re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", line):
            errors.append(f"Line {number}: {line!r} â€” use DD/MM/YYYY.")
            continue
        try:
            dates.append(datetime.strptime(line, "%d/%m/%Y").date())
        except ValueError:
            errors.append(f"Line {number}: {line!r} â€” invalid calendar date.")
    return sorted(set(dates)), errors, len(dates) - len(set(dates))


def build_daily(start, end, failures):
    """Start with zero prior days; a failure is zero, next successful day is one."""
    failures = set(failures)
    rows, streak = [], 0
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        failed = day in failures
        streak = 0 if failed else streak + 1
        rows.append({"Date": pd.Timestamp(day), "Streak": streak,
                     "Failed": failed, "Weekday": WEEKDAYS[day.weekday()]})
    return pd.DataFrame(rows)


def weekday_summary(daily):
    summary = daily.groupby("Weekday").agg(
        Failures=("Failed", "sum"), Days=("Failed", "size")
    ).reindex(WEEKDAYS, fill_value=0).reset_index()
    summary["Failure rate (%)"] = (100 * summary["Failures"] /
                                    summary["Days"].replace(0, float("nan")))
    return summary


def main():
    st.set_page_config(page_title="PMO Streak Tracker", layout="wide")
    st.title("PMO streak tracker")
    st.caption("Track your progress, notice patterns, and keep going one day at a time.")
    today = datetime.now(ZoneInfo("Africa/Cairo")).date()

    with st.sidebar:
        st.header("Your log")
        upload = st.file_uploader("Load a saved date log", type=["txt"])
        if upload is not None:
            try:
                uploaded_text = upload.getvalue().decode("utf-8-sig")
            except UnicodeDecodeError:
                st.error("Please upload a UTF-8 text file.")
                st.stop()
            if st.button("Use uploaded log"):
                st.session_state["failure_text"] = uploaded_text
        text = st.text_area("Failure dates (DD/MM/YYYY)", value=EXAMPLE,
                            height=260, key="failure_text")
        failures, errors, duplicates = parse_dates(text)
        if errors:
            for error in errors:
                st.error(error)
            st.stop()
        if any(day > today for day in failures):
            st.error("Failure dates cannot be in the future.")
            st.stop()
        if duplicates:
            st.info(f"Ignored {duplicates} duplicate date(s). Each date counts once.")
        start = st.date_input("Tracking start date", value=min(failures) if failures else today,
                              max_value=today, format="DD/MM/YYYY")
        end = st.date_input("Chart through", value=today, min_value=start,
                            max_value=today, format="DD/MM/YYYY")
        st.caption("Set the start to your actual first tracking day. No streak before that date is inferred.")
        log = "Failed on:\n" + "\n".join(day.strftime("%d/%m/%Y") for day in failures)
        st.download_button("Save date log", log, "pmo_failure_dates.txt", "text/plain")
        st.caption("Edits last for this session. Save your log and upload it next time.")

    daily = build_daily(start, end, failures)
    summary = weekday_summary(daily)
    excluded = sum(not start <= day <= end for day in failures)
    if excluded:
        st.info(f"{excluded} logged failure date(s) fall outside the selected range and are excluded from the charts.")
    if end == today and today not in failures:
        st.caption("Today is included as a successful day unless logged as a failure. Select yesterday to show only completed days.")
    st.caption("Every unlisted date in the tracking range is assumed successful. Multiple failures on one date count as one failure day.")
    cols = st.columns(4)
    cols[0].metric("Streak at selected end", f"{int(daily.iloc[-1]['Streak'])} days")
    cols[1].metric("Longest streak in range", f"{int(daily['Streak'].max())} days")
    cols[2].metric("Failure days", int(daily["Failed"].sum()))
    cols[3].metric("Successful days", int((~daily["Failed"]).sum()))

    st.subheader("Daily streak")
    chart = go.Figure()
    chart.add_trace(go.Scatter(x=daily["Date"], y=daily["Streak"], mode="lines",
                              name="Streak", line=dict(color="#14b8a6", width=3),
                              fill="tozeroy", fillcolor="rgba(20,184,166,0.10)",
                              hovertemplate="%{x|%d/%m/%Y}<br>Streak: %{y} days<extra></extra>"))
    failed = daily[daily["Failed"]]
    chart.add_trace(go.Scatter(x=failed["Date"], y=failed["Streak"], mode="markers",
                              name="Failure day", marker=dict(color="#f87171", size=3, symbol="o"),
                              hovertemplate="%{x|%d/%m/%Y}<br>Failure â€” streak reset to 0<extra></extra>"))
    chart.update_layout(height=370, margin=dict(l=20, r=20, t=15, b=20),
                        xaxis_title="Date", yaxis_title="Consecutive successful days",
                        legend=dict(orientation="h", y=1.12), hovermode="x unified")
    chart.update_yaxes(rangemode="tozero", dtick=1 if daily["Streak"].max() <= 20 else None)
    st.plotly_chart(chart, width="stretch")

    st.subheader("Failure patterns by weekday")
    mode = st.radio("Compare weekdays by", ["Failure count", "Failure rate"], horizontal=True)
    field = "Failures" if mode == "Failure count" else "Failure rate (%)"
    bars = go.Figure(go.Bar(x=summary["Weekday"], y=summary[field],
                           marker_color="#a78bfa", customdata=summary[["Failures", "Days"]],
                           hovertemplate="%{x}<br>%{customdata[0]} failure day(s) / %{customdata[1]} tracked day(s)<br>Value: %{y:.2f}<extra></extra>"))
    bars.update_layout(height=340, margin=dict(l=20, r=20, t=15, b=20), yaxis_title=field,
                       xaxis_title="Weekday")
    bars.update_yaxes(rangemode="tozero", dtick=1 if field == "Failures" else None)
    st.plotly_chart(bars, width="stretch")
    if int(summary["Failures"].sum()):
        maximum = summary["Failures"].max()
        leaders = summary.loc[summary["Failures"] == maximum, "Weekday"].tolist()
        st.info(f"Most logged failure days: {', '.join(leaders)} ({int(maximum)} each).")
    else:
        st.success("No failure days logged in this range.")
    with st.expander("View daily data and export"):
        #st.dataframe(daily, hide_index=True, width="stretch")
        #st.download_button("Download daily CSV", daily.to_csv(index=False),
        #                   "pmo_daily_streak.csv", "text/csv")
        st.dataframe(summary, hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
