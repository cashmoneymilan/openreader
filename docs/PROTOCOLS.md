# Milestone 0 protocol decisions

## CrossPoint

- Default discovery target: `http://crosspoint.local`, with `http://192.168.4.1` as hotspot fallback.
- Status: `GET /api/status`.
- Inventory: `GET /api/files?path=/Books` returns filename, size, directory status, and EPUB status.
- Upload/replace: `POST /upload?path=/Books` with multipart field `file`; an existing filename is overwritten.
- Readback: `GET /download?path=/Books/file.epub` permits SHA-256 verification.
- Delete: `POST /delete` with form field `path`.
- Device service is reachable only during File Transfer or Calibre Wireless mode and has no authentication. OpenReader therefore models a user-initiated sync session and warns users to use a controlled network.

Primary references:

- https://github.com/crosspoint-reader/crosspoint-reader/blob/develop/docs/webserver-endpoints.md
- https://github.com/crosspoint-reader/crosspoint-reader/blob/develop/docs/webserver.md

## Stock Xteink firmware

- Default target: `http://192.168.3.3` while connected to the device hotspot.
- Inventory: `GET /list?dir=/Books` returns names and entry types but no file sizes.
- Upload/replace: `POST /edit` with multipart field `data`; the multipart filename carries the full destination path.
- Delete: `DELETE /edit` with multipart field `path`.
- Because stock listing omits size and no readback endpoint is established, a successful upload is `upload_acknowledged`, not `listed_on_device` or `verified_readback`.

Protocol implementation reference:

- https://github.com/jtvargas/crosspoint-app/blob/main/SendToX4/Services/StockFirmwareService.swift
