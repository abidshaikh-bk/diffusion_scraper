# Directory Structure for `C:\Users\AbidShaikh\Documents\video_scraper_system`

```
video_scraper_system
├── app
│   ├── core
│   │   ├── human_sleep.py
│   │   ├── logger.py
│   │   ├── network.py
│   │   ├── retry.py
│   │   └── utils.py
│   ├── discovery
│   │   ├── discovery_runner.py
│   │   ├── playwright_dailymotion_search.py
│   │   ├── playwright_vimeo_search.py
│   │   └── youtube_ytdlp_search.py
│   ├── downloader
│   │   ├── dailymotion_downloader.py
│   │   ├── dispatcher.py
│   │   ├── path_builder.py
│   │   ├── vimeo_downloader.py
│   │   └── ytdlp_downloader.py
│   ├── duplicates
│   │   └── sheet_dedupe.py
│   ├── filtering
│   │   ├── duration_filter.py
│   │   ├── keyword_filter.py
│   │   └── pipeline.py
│   ├── models
│   │   └── video_metadata.py
│   ├── pipeline
│   │   │   └── worker.cpython-314.pyc
│   │   └── worker.py
│   ├── platforms
│   │   └── registry.py
│   ├── scrapers
│   │   ├── ytdlp_auth.py
│   │   └── ytdlp_scraper.py
│   └── sync
│       ├── oauth.py
│       ├── sheet_schema.py
│       ├── sheets_client.py
│       └── sync_manager.py
├── configs
│   ├── config.yaml
│   ├── discovery.yaml
│   ├── keywords.yaml
│   └── platforms.yaml
├── data
│   ├── downloads
│   │   └── YouTube
│   └── logs
│       └── worker.log
├── scripts
│   ├── debug_pending.py
│   ├── discover_and_enqueue.py
│   ├── enqueue_from_file.py
│   ├── enqueue_from_file_to_sheet.py
│   ├── init_sheet_headers.py
│   ├── run_worker.py
│   ├── test_download.py
│   ├── test_metadata.py
│   └── test_relevance.py
├── secrets
│   ├── client_secret.json
│   └── token.json
├── .env
├── .gitignore
├── doc.md
├── requirements.txt
└── yt-cookies.txt
```