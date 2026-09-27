# Artwork Handling — Current Build

## YouTube Music fallback

YouTube Music can expose ordinary `i.ytimg.com` thumbnails that are 16:9 or padded, while a page-level image can be square album art. The implementation therefore downloads all yt-dlp thumbnail variants, optionally fetches the YTMusic page OpenGraph image, prefers valid square candidates, and normalizes the YTMusic fallback to square JPEG.

Source example: https://github.com/yt-dlp/yt-dlp/issues/11660

## Spotify primary artwork

When Spotify enrichment is enabled and a duration-matching Spotify track is selected, the full Spotify album object is read and the largest album image is selected. Spotify documents album images in multiple sizes.

The selected Spotify artwork is treated differently from the YTMusic fallback: it is downloaded and then preserved byte-for-byte. The project does **not** crop, resize, recompress, sharpen, recolor, or otherwise transform it. If the returned image is not a valid square album cover, the pipeline refuses to modify it and falls back to the YTMusic artwork instead.

Spotify documentation: https://developer.spotify.com/documentation/web-api/reference/get-an-album

The exact source URL, dimensions, MIME type, byte size and SHA-256 are recorded in the sidecar JSON.
