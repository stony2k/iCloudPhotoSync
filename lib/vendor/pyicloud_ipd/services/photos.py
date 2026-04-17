"""PhotosService — iCloud Photos via CloudKit API."""
import base64
import json
import logging

LOGGER = logging.getLogger(__name__)

# Smart album filter values: (query_filter for photos, count_key for HyperionIndexCountLookup)
# Apple uses UPPERCASE for photo queries but mixed-case for count queries
SMART_FOLDERS = {
    "Favorites": ("FAVORITE", "Favorite"),
    "Videos": ("VIDEO", "Video"),
    "Screenshots": ("SCREENSHOT", "Screenshot"),
    "Live": ("LIVE", "Live"),
    "Panoramas": ("PANORAMA", "Panorama"),
    "Time-lapse": ("TIME-LAPSE", "Time-lapse"),
    "Slo-mo": ("SLO-MO", "Slo-mo"),
    "Bursts": ("BURST", "Burst"),
}


class PhotoAlbum:
    """Represents an iCloud Photos album."""

    def __init__(self, service, name, record_name=None, album_type="user",
                 smart_filter=None, smart_count_key=None,
                 list_type=None, obj_type=None):
        self.service = service
        self.name = name
        self.record_name = record_name
        self.album_type = album_type  # "all", "user", "smart"
        self.smart_filter = smart_filter
        self._photo_count = None

        if album_type == "all":
            self.list_type = "CPLAssetAndMasterByAssetDateWithoutHiddenOrDeleted"
            self.obj_type = "CPLAssetByAssetDateWithoutHiddenOrDeleted"
        elif album_type == "smart":
            self.list_type = "CPLAssetAndMasterInSmartAlbumByAssetDate"
            # Count query uses mixed-case, photo query uses UPPERCASE
            self.obj_type = "CPLAssetInSmartAlbumByAssetDate:%s" % (smart_count_key or smart_filter)
        elif album_type == "user":
            self.list_type = "CPLContainerRelationLiveByAssetDate"
            self.obj_type = "CPLContainerRelationNotDeletedByAssetDate:%s" % record_name
        else:
            self.list_type = list_type
            self.obj_type = obj_type

    @property
    def photo_count(self):
        if self._photo_count is None:
            self._photo_count = self.service._get_album_count(self.obj_type)
        return self._photo_count

    def photos(self, limit=200, offset=0, direction="ASCENDING"):
        """Fetch photos in this album."""
        return self.service._get_album_photos(self, limit=limit, offset=offset, direction=direction)

    def __repr__(self):
        return "<PhotoAlbum: %s>" % self.name


class PhotoAsset:
    """Represents a single photo/video asset."""

    def __init__(self, master_record, asset_record=None):
        self._master = master_record
        self._asset = asset_record
        self._parse()

    def _parse(self):
        m = self._master.get("fields", {})
        a = self._asset.get("fields", {}) if self._asset else {}

        # Filename
        raw = m.get("filenameEnc", {}).get("value", "")
        try:
            self.filename = base64.b64decode(raw).decode("utf-8")
        except Exception:
            self.filename = raw

        # Dates
        self.created = a.get("assetDate", {}).get("value", 0)
        self.added = a.get("addedDate", {}).get("value", 0)

        # Type
        self.item_type = m.get("itemType", {}).get("value", "public.jpeg")
        self.is_video = "movie" in self.item_type or "video" in self.item_type

        # Dimensions
        self.width = m.get("resOriginalWidth", {}).get("value", 0)
        self.height = m.get("resOriginalHeight", {}).get("value", 0)

        # Size and checksum from original resource
        res = m.get("resOriginalRes", {}).get("value", {})
        self.size = res.get("size", 0)
        self.checksum = res.get("fileChecksum", "")

        # Record name for identification
        self.id = self._master.get("recordName", "")

    @staticmethod
    def _fix_url(url):
        """Replace ${f} placeholder in iCloud download URLs."""
        if url and "${f}" in url:
            return url.replace("${f}", "image.jpg")
        return url

    @property
    def thumb_url(self):
        """URL for JPEG thumbnail."""
        m = self._master.get("fields", {})
        thumb = m.get("resJPEGThumbRes", {}).get("value", {})
        return self._fix_url(thumb.get("downloadURL"))

    @property
    def medium_url(self):
        """URL for medium JPEG."""
        m = self._master.get("fields", {})
        med = m.get("resJPEGMedRes", {}).get("value", {})
        return self._fix_url(med.get("downloadURL"))

    @property
    def original_url(self):
        """URL for original file."""
        m = self._master.get("fields", {})
        orig = m.get("resOriginalRes", {}).get("value", {})
        return self._fix_url(orig.get("downloadURL"))

    def to_dict(self):
        """Serializable dict for JSON responses."""
        return {
            "id": self.id,
            "filename": self.filename,
            "created": self.created,
            "item_type": self.item_type,
            "is_video": self.is_video,
            "width": self.width,
            "height": self.height,
            "size": self.size,
            "checksum": self.checksum,
            "thumb_url": self.thumb_url,
            "medium_url": self.medium_url,
            "original_url": self.original_url,
        }

    def __repr__(self):
        return "<PhotoAsset: %s>" % self.filename


class PhotosService:
    """iCloud Photos service via CloudKit API."""

    ZONE_ID = {"zoneName": "PrimarySync"}

    def __init__(self, service_root, session, params):
        self.session = session
        self.params = dict(params)
        self.params.update({
            "remapEnums": "true",
            "getCurrentSyncToken": "true",
        })
        self._service_endpoint = (
            "%s/database/1/com.apple.photos.cloud/production/private"
            % service_root
        )
        self._albums = None

    def _query(self, payload):
        """Execute a CloudKit records query."""
        url = "%s/records/query" % self._service_endpoint
        response = self.session.post(
            url,
            params=self.params,
            data=json.dumps(payload),
            headers={"Content-Type": "text/plain"},
        )
        data = response.json()
        self._check_cloudkit_adp(data)
        return data

    def _lookup_records(self, record_names):
        """Fetch records by recordName via CloudKit records/lookup."""
        url = "%s/records/lookup" % self._service_endpoint
        payload = {
            "records": [
                {"recordName": rn, "zoneID": self.ZONE_ID}
                for rn in record_names
            ],
        }
        response = self.session.post(
            url,
            params=self.params,
            data=json.dumps(payload),
            headers={"Content-Type": "text/plain"},
        )
        return response.json()

    def refresh_photo_url(self, photo):
        """Re-fetch a photo's master record to get fresh download URLs.

        Returns a new URL or None if the lookup fails.
        """
        try:
            data = self._lookup_records([photo.id])
            for record in data.get("records", []):
                if record.get("recordName") == photo.id:
                    orig = record.get("fields", {}).get(
                        "resOriginalRes", {}).get("value", {})
                    url = orig.get("downloadURL")
                    if url:
                        photo._master = record
                        return PhotoAsset._fix_url(url)
        except Exception:
            LOGGER.exception("Failed to refresh URL for %s", photo.id)
        return None

    def _batch_query(self, payload):
        """Execute a CloudKit batch query."""
        url = "%s/internal/records/query/batch" % self._service_endpoint
        response = self.session.post(
            url,
            params=self.params,
            data=json.dumps(payload),
            headers={"Content-Type": "text/plain"},
        )
        data = response.json()
        self._check_cloudkit_adp(data)
        return data

    @staticmethod
    def _check_cloudkit_adp(data):
        """Detect CloudKit errors that indicate ADP is blocking access."""
        from pyicloud_ipd.exceptions import PyiCloudADPProtectionException
        if not isinstance(data, dict):
            return
        for record in data.get("records", []):
            reason = record.get("serverErrorCode", "")
            if reason in ("ACCESS_DENIED", "PRIVATE_DB_DISABLED",
                          "ZONE_NOT_FOUND"):
                raise PyiCloudADPProtectionException(reason)

    def check_indexing(self):
        """Check if Photos library indexing is complete."""
        data = self._query({
            "query": {"recordType": "CheckIndexingState"},
            "zoneID": self.ZONE_ID,
        })
        records = data.get("records", [])
        if records:
            state = records[0].get("fields", {}).get("state", {}).get("value")
            return state == "FINISHED"
        return False

    @property
    def albums(self):
        """Returns dict of album name -> PhotoAlbum."""
        if self._albums is not None:
            return self._albums

        self._albums = {}

        # "All Photos" built-in
        self._albums["All Photos"] = PhotoAlbum(
            self, "All Photos", album_type="all"
        )

        # Smart folders
        for name, (query_filter, count_key) in SMART_FOLDERS.items():
            self._albums[name] = PhotoAlbum(
                self, name, album_type="smart",
                smart_filter=query_filter, smart_count_key=count_key,
            )

        # User-created albums
        try:
            data = self._query({
                "query": {"recordType": "CPLAlbumByPositionLive"},
                "zoneID": self.ZONE_ID,
            })
            for record in data.get("records", []):
                rn = record.get("recordName", "")
                if rn in ("----Root-Folder----", "----Project-Root-Folder----"):
                    continue
                fields = record.get("fields", {})
                if fields.get("isDeleted", {}).get("value"):
                    continue
                raw_name = fields.get("albumNameEnc", {}).get("value", "")
                try:
                    name = base64.b64decode(raw_name).decode("utf-8")
                except Exception:
                    name = raw_name
                if name:
                    self._albums[name] = PhotoAlbum(
                        self, name, record_name=rn, album_type="user"
                    )
        except Exception:
            LOGGER.exception("Failed to fetch user albums")

        return self._albums

    def _get_album_count(self, obj_type):
        """Get photo count for an album by its obj_type."""
        try:
            data = self._batch_query({
                "batch": [{
                    "resultsLimit": 1,
                    "query": {
                        "filterBy": {
                            "fieldName": "indexCountID",
                            "fieldValue": {
                                "type": "STRING_LIST",
                                "value": [obj_type],
                            },
                            "comparator": "IN",
                        },
                        "recordType": "HyperionIndexCountLookup",
                    },
                    "zoneWide": True,
                    "zoneID": self.ZONE_ID,
                }],
            })
            records = data.get("batch", [{}])[0].get("records", [])
            if records:
                return records[0].get("fields", {}).get("itemCount", {}).get("value", 0)
        except Exception:
            LOGGER.exception("Failed to get album count for %s", obj_type)
        return 0

    def _get_album_photos(self, album, limit=200, offset=0, direction="ASCENDING"):
        """Fetch photos in an album. Returns list of PhotoAsset.

        CloudKit often returns partial batches (far fewer than requested).
        We iterate internally, advancing startRank by the actual number of
        photos returned, until we've collected `limit` photos or CloudKit
        returns nothing.
        """
        result = []
        current_offset = offset
        # Guard against pathological loops — cap total HTTP calls per request.
        for _ in range(max(limit, 20)):
            if len(result) >= limit:
                break

            filters = [
                {
                    "fieldName": "startRank",
                    "fieldValue": {"type": "INT64", "value": current_offset},
                    "comparator": "EQUALS",
                },
                {
                    "fieldName": "direction",
                    "fieldValue": {"type": "STRING", "value": direction},
                    "comparator": "EQUALS",
                },
            ]

            if album.album_type == "user":
                filters.append({
                    "fieldName": "parentId",
                    "comparator": "EQUALS",
                    "fieldValue": {"type": "STRING", "value": album.record_name},
                })
            elif album.album_type == "smart":
                filters.append({
                    "fieldName": "smartAlbum",
                    "comparator": "EQUALS",
                    "fieldValue": {"type": "STRING", "value": album.smart_filter},
                })

            remaining = limit - len(result)
            data = self._query({
                "query": {
                    "filterBy": filters,
                    "recordType": album.list_type,
                },
                "resultsLimit": max(remaining * 2, 4),
                "zoneID": self.ZONE_ID,
            })

            masters = {}
            assets = {}
            for record in data.get("records", []):
                rt = record.get("recordType", "")
                rn = record.get("recordName", "")
                if rt == "CPLMaster":
                    masters[rn] = record
                elif rt == "CPLAsset":
                    ref = record.get("fields", {}).get(
                        "masterRef", {}
                    ).get("value", {}).get("recordName")
                    if ref:
                        assets[ref] = record

            batch = []
            for master_id, master in masters.items():
                asset = assets.get(master_id)
                batch.append(PhotoAsset(master, asset))

            if not batch:
                break  # end of album

            result.extend(batch)
            step = len(batch) if direction == "ASCENDING" else -len(batch)
            current_offset += step
            if current_offset < 0:
                break

        return result[:limit]
