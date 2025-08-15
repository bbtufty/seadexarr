#!/usr/bin/env python3
"""
Legacy entry point for SeaDexArr - DEPRECATED

This file is maintained for backward compatibility only.
Please use the new modern CLI instead:

    seadexarr --help
    seadexarr sync sonarr username
    seadexarr sync radarr username
    seadexarr config-validate
    seadexarr status

The new CLI provides better functionality, error handling, and user experience.
"""

import sys
import warnings


def main():
    warnings.warn(
        "seadexarr.py is deprecated. Use the new CLI: 'seadexarr --help'",
        DeprecationWarning,
        stacklevel=2,
    )

    print("🚨 DEPRECATED: Legacy seadexarr.py detected!")
    print("")
    print("Please use the new modern CLI instead:")
    print("")
    print("  # Basic sync commands")
    print("  seadexarr sync sonarr myusername")
    print("  seadexarr sync radarr myusername --dry-run")
    print("")
    print("  # Batch processing")
    print("  seadexarr sync-batch user1 user2 user3 --target=sonarr")
    print("")
    print("  # Configuration and status")
    print("  seadexarr config-validate")
    print("  seadexarr status")
    print("")
    print("  # Search releases")
    print('  seadexarr search-releases "Attack on Titan"')
    print("")
    print("  # Get help")
    print("  seadexarr --help")
    print("")
    print("The new CLI offers:")
    print("  ✅ Better error handling and validation")
    print("  ✅ Rich, colorful output with progress bars")
    print("  ✅ Comprehensive configuration management")
    print("  ✅ Async performance improvements")
    print("  ✅ Backward compatibility support")
    print("")

    # For Docker compatibility, try to run the new CLI if arguments were passed
    if len(sys.argv) > 1:
        try:
            from seadexarr.cli.main import app

            print("🔄 Attempting to run new CLI...")

            # Convert legacy --arr argument to new format
            if "--arr" in sys.argv:
                idx = sys.argv.index("--arr")
                if idx + 1 < len(sys.argv):
                    arr_type = sys.argv[idx + 1]
                    print(
                        f"⚠️  Legacy --arr {arr_type} detected. Use 'seadexarr sync {arr_type} USERNAME' instead."
                    )
                    sys.exit(1)

            # Run the new CLI
            app()

        except ImportError as e:
            print(f"❌ Failed to import new CLI: {e}")
            print("Please install the latest version: pip install --upgrade seadexarr")
            sys.exit(1)
    else:
        print("Use 'seadexarr --help' to see all available commands.")
        sys.exit(1)


if __name__ == "__main__":
    main()
