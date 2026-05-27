#!/usr/bin/env python3
"""
Growth Stock Screener Runner Script

This script resolves Python path issues.
"""

import os
import sys
import argparse
import subprocess

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def main():
    """Parse command line arguments and run the main screener."""
    parser = argparse.ArgumentParser(
        description="Growth Stock Screener - A tool for screening growth stocks using SEC EDGAR data"
    )
    
    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "download",
            "parse",
            "enrich",
            "leadership",
            "financials",
            "screen",
            "status",
            "update",
            "analyze",
            "tv-export",
            "web",
            "profile-sweep",
        ],
        help="Operation mode: download SEC data, parse data, enrich data, screen stocks, export TradingView artifacts, inspect status, update missing stages, screen every profile, or serve the web dashboard"
    )
    
    parser.add_argument(
        "--config",
        default=os.path.join("config", "config.json"),
        help="Path to configuration file (default: config/config.json)"
    )

    parser.add_argument(
        "--profile",
        help="Optional screener profile name under config/profiles, e.g. canslim_pure"
    )

    parser.add_argument(
        "--ticker",
        help="Ticker to analyze when --mode analyze is used"
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for --mode web (default: 127.0.0.1)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for --mode web (default: 8765)"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress HTTP request logs when --mode web is used"
    )

    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow --mode web to bind to a non-loopback host"
    )

    parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="Open the dashboard in a browser when --mode web is used"
    )

    parser.add_argument(
        "--auth",
        help="Require HTTP Basic authentication for --mode web, formatted as USER:PASSWORD"
    )

    parser.add_argument(
        "--auth-env",
        default="CANSLIM_DASHBOARD_AUTH",
        help="Read Basic Auth credentials from this environment variable when --auth is omitted"
    )

    parser.add_argument(
        "--require-auth",
        action="store_true",
        help="Refuse to start --mode web unless Basic Auth credentials are configured"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO)"
    )
    
    args = parser.parse_args()

    if args.mode == "web":
        from src.web.server import run as run_web_dashboard

        try:
            run_web_dashboard(
                args.host,
                args.port,
                quiet=args.quiet,
                allow_remote=args.allow_remote,
                open_browser=args.open_browser,
                auth=args.auth,
                auth_env=args.auth_env,
                require_auth=args.require_auth,
            )
        except ValueError as exc:
            parser.error(str(exc))
        return

    if args.mode == "profile-sweep":
        _run_profile_sweep(args.config, args.log_level)
        return
    
    # Run main screener
    from src.growth_stock_screener import main as run_screener
    
    # Pass arguments correctly
    sys.argv = [sys.argv[0], "--mode", args.mode, "--config", args.config, "--log-level", args.log_level]
    if args.profile:
        sys.argv.extend(["--profile", args.profile])
    if args.ticker:
        sys.argv.extend(["--ticker", args.ticker])
    run_screener()


def _run_profile_sweep(config_path: str, log_level: str) -> None:
    """Run the screen stage once for every configured profile."""
    resolved_config = os.path.abspath(config_path)
    profile_dir = os.path.join(os.path.dirname(resolved_config), "profiles")
    try:
        profile_names = sorted(
            os.path.splitext(filename)[0]
            for filename in os.listdir(profile_dir)
            if filename.endswith(".json")
        )
    except FileNotFoundError as exc:
        raise SystemExit(f"Profile directory not found: {profile_dir}") from exc

    if not profile_names:
        raise SystemExit(f"No profile JSON files found under {profile_dir}")

    failures = []
    runner = os.path.abspath(__file__)
    for index, profile in enumerate(profile_names, start=1):
        print(f"[profile-sweep] {index}/{len(profile_names)} screen {profile}", flush=True)
        command = [
            sys.executable,
            runner,
            "--mode",
            "screen",
            "--config",
            resolved_config,
            "--profile",
            profile,
            "--log-level",
            log_level,
        ]
        completed = subprocess.run(command)
        if completed.returncode != 0:
            failures.append((profile, completed.returncode))

    if failures:
        failed = ", ".join(f"{profile}({returncode})" for profile, returncode in failures)
        raise SystemExit(f"profile-sweep failed for: {failed}")

    print(f"[profile-sweep] completed {len(profile_names)} profile(s)", flush=True)

if __name__ == "__main__":
    main()
