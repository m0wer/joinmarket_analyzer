"""Statistics and visualization module for JoinMarket analysis."""

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px
from loguru import logger

from joinmarket_analyzer.db import init_db


def load_data(db_path: str) -> pd.DataFrame:
    """Load data from the database into a pandas DataFrame."""
    if not Path(db_path).exists():
        logger.error(f"Database file not found: {db_path}")
        return pd.DataFrame()

    engine = init_db(db_path)

    # Use pandas read_sql to load tables
    try:
        # Load CoinJoin transactions
        df_tx = pd.read_sql("SELECT * FROM coinjointx", engine)

        # Load Analysis results
        df_analysis = pd.read_sql("SELECT * FROM analysissummary", engine)

        if df_tx.empty:
            logger.warning("No transactions found in database.")
            return pd.DataFrame()

        # Merge dataframes
        # Left join to keep all found CJs even if analysis failed or wasn't run
        df = pd.merge(df_tx, df_analysis, on="txid", how="left")

        # Convert timestamp to datetime
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")

        return df
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return pd.DataFrame()


def print_cli_stats(df: pd.DataFrame) -> None:
    """Print summary statistics to the CLI."""
    if df.empty:
        return

    total_txs = len(df)
    analyzed_txs = df["success"].count()
    successful_solves = df[df["success"].fillna(False).astype(bool)].shape[0]

    # Basic Stats
    print("\n" + "=" * 50)
    print("JOINMARKET COINJOIN STATISTICS")
    print("=" * 50)
    print(f"Total CoinJoins found: {total_txs}")
    print(f"Analyzed: {analyzed_txs}")
    print(f"Successfully Solved: {successful_solves} ({successful_solves / total_txs * 100:.1f}%)")

    # Volume (Equal Amount * Participants)
    # Note: This is "mixed volume" approximation
    df["mixed_volume"] = df["equal_amount"] * df["num_participants"]
    total_volume_sats = df["mixed_volume"].sum()
    total_volume_btc = total_volume_sats / 1e8

    print(f"Total Mixed Volume: {total_volume_btc:,.2f} BTC")

    # Participants
    avg_participants = df["num_participants"].mean()
    print(f"Avg Participants: {avg_participants:.1f}")

    # Fees
    if "estimated_taker_fee" in df.columns:
        valid_fees = df[df["estimated_taker_fee"].notna()]
        if not valid_fees.empty:
            avg_taker_fee = valid_fees["estimated_taker_fee"].mean()
            print(f"Avg Taker Fee: {avg_taker_fee:,.0f} sats")

    if "total_maker_fees" in df.columns:
        # Note: AnalysisSummary doesn't have total_maker_fees directly,
        # but we can infer or use what we have.
        # Actually AnalysisSummary has min/max/avg maker fees per maker.
        # We can sum them up? No, those are per-maker.
        # Let's use estimated_taker_fee - network_fee as total maker fees roughly

        valid_sol = df[df["success"].fillna(False).astype(bool)].copy()
        if not valid_sol.empty:
            valid_sol["total_maker_fees_est"] = (
                valid_sol["estimated_taker_fee"] - valid_sol["network_fee"]
            )
            total_fees_earned = valid_sol["total_maker_fees_est"].sum()
            print(f"Total Maker Fees Earned (Est): {total_fees_earned / 1e8:,.4f} BTC")

    # Max Relative Fee
    if "max_maker_fees" in df.columns and "equal_amount" in df.columns:
        valid_rel = df[(df["max_maker_fees"].notna()) & (df["equal_amount"] > 0)].copy()
        if not valid_rel.empty:
            valid_rel["max_rel_fee"] = valid_rel["max_maker_fees"] / valid_rel["equal_amount"]
            max_rel_fee_observed = valid_rel["max_rel_fee"].max()
            avg_rel_fee_limit = valid_rel["max_rel_fee"].mean()

            print(
                f"Max Relative Fee Observed: {max_rel_fee_observed:.5f} "
                f"({max_rel_fee_observed * 100:.3f}%)"
            )
            print(
                f"Avg Max Relative Fee (Limit): {avg_rel_fee_limit:.5f} "
                f"({avg_rel_fee_limit * 100:.3f}%)"
            )

    print("=" * 50 + "\n")


def generate_charts(df: pd.DataFrame, output_file: str = "joinmarket_stats.html"):
    """Generate interactive charts using Plotly."""
    if df.empty:
        return

    logger.info(f"Generating charts to {output_file}...")

    # 1. Frequency over time (Weekly)
    df_weekly = df.set_index("datetime").resample("W").size().reset_index(name="count")
    fig_freq = px.bar(df_weekly, x="datetime", y="count", title="CoinJoin Frequency (Weekly)")

    # 2. Volume over time (Weekly)
    df["mixed_volume_btc"] = (df["equal_amount"] * df["num_participants"]) / 1e8
    df_vol = df.set_index("datetime").resample("W")["mixed_volume_btc"].sum().reset_index()
    fig_vol = px.bar(
        df_vol, x="datetime", y="mixed_volume_btc", title="Mixed Volume (BTC) (Weekly)"
    )

    # 3. Participants Distribution
    fig_part = px.histogram(df, x="num_participants", title="Participants Distribution", nbins=20)

    # 4. Relative Fee Limit Heatmap/Scatter
    # We want to see what relative fee limits are used over time or vs amount
    figs = [fig_freq, fig_vol, fig_part]

    if "max_maker_fees" in df.columns:
        df_fees = df[
            (df["success"].fillna(False).astype(bool)) & (df["max_maker_fees"].notna())
        ].copy()
        if not df_fees.empty:
            df_fees["rel_fee_limit"] = df_fees["max_maker_fees"] / df_fees["equal_amount"]

            # Scatter: Amount vs Relative Fee Limit
            fig_fee_scatter = px.scatter(
                df_fees,
                x="equal_amount",
                y="rel_fee_limit",
                color="num_participants",
                log_x=True,
                log_y=True,
                hover_data=["txid", "datetime"],
                title="Relative Fee Limit vs Equal Amount (Log Scale)",
            )
            figs.append(fig_fee_scatter)

            # Histogram of relative fees
            fig_fee_hist = px.histogram(
                df_fees, x="rel_fee_limit", title="Relative Fee Limit Distribution", nbins=50
            )
            figs.append(fig_fee_hist)

    # Combine into single HTML
    with open(output_file, "w") as f:
        f.write("<html><head><title>JoinMarket Stats</title></head><body>")
        f.write("<h1>JoinMarket Transaction Analysis Stats</h1>")
        for fig in figs:
            f.write(fig.to_html(full_html=False, include_plotlyjs="cdn"))
        f.write("</body></html>")

    logger.success(f"Charts saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate statistics and charts for JoinMarket analysis"
    )
    parser.add_argument("--db", default="joinmarket_stats.db", help="Database file path")
    parser.add_argument(
        "--html", default="joinmarket_stats.html", help="Output HTML file for charts"
    )
    parser.add_argument("--no-charts", action="store_true", help="Skip chart generation")

    args = parser.parse_args()

    df = load_data(args.db)
    if df.empty:
        return

    print_cli_stats(df)

    if not args.no_charts:
        generate_charts(df, args.html)


if __name__ == "__main__":
    main()
