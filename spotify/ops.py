"""Pathfinder persisted-query registry: operationName -> sha256 hashes.

The open.spotify.com web player talks to https://api-partner.spotify.com/
pathfinder/v1/query with APQ persisted queries: the client never sends the
query text, only `operationName` + `extensions.persistedQuery.sha256Hash`.
The hashes live in the player's JS chunks as
    new X.l("<operationName>","query","<sha256>",null)
and change whenever Spotify edits a query. Some operations have two hashes
(desktop `xpui-*` chunk vs `mobile-web-player`); both are valid and return
slightly different field sets, so the order below is "preferred first".

Captured 2026-09-19 (web-player 1.3.3.52) and validated live. When a hash
dies the gateway answers 200 + `errors[0].message == "PersistedQueryNotFound"`
and fetch.pathfinder() tries the next one, then re-scans the chunk
manifest (fetch.discover_hashes) for a fresh hash before giving up.
"""

HASHES = {
    # tracks
    "getTrack": ["a8ef9e9f02b836feb0da3003c31dbb30decc6f4b473ef89ca88c882386d668de"],
    "decorateContextTracks": ["383de00240775c39a6afe0b1055dc562b2a3930894201f9762f3fc32a74971c7"],
    "trackPreview": ["fc26ffc7a1a4f93bd4c2d705649f7dba1de34005b3dc2915549847a9959405d8"],
    "queryTrackCreditsGroupedModal": ["f135fb9be58a72d041ab5d214d817021a272405d883860468e2627afb01a3ca9"],
    "canvas": ["575138ab27cd5c1b3e54da54d0a7cc8d85485402de26340c2145f0f6bb5e7a9f"],
    "internalLinkRecommenderTrack": ["c77098ee9d6ee8ad3eb844938722db60570d040b49f41f5ec6e7be9160a7c86b"],
    "similarAlbumsBasedOnThisTrack": ["1d1f93a737498adca2c892c73af87fc0b052afe4e1a33c989540c32413dfae17"],
    # albums
    "getAlbum": ["6a74b456cd1735c9193d9e8ec8cc5184cad7ce13572210315229db3975964361"],
    "albumPreRelease": ["e1a5537a42c3b8a687f10ae865c3b6776d6d797f8c0c272b2d40dc159a8e1a94"],
    "albumPreReleaseTracks": ["dfbdcf2688995adc2c2196fcdd7802b2a5137a2549b361aa7fb23cd6493f4672"],
    # artists
    "queryArtistOverview": ["1ac33ddab5d39a3a9c27802774e6d78b9405cc188c6f75aed007df2a32737c72",
                            "9f8134ef565e78621f1e1793555bd6633c5ac144ae0f89604ed3ae3f80b3c8e6"],
    "queryArtistAboutModal": ["702e29a866e0b4b4fabdf974454512a2c32d93643b1969b7a3a0dd92084f05f6"],
    "queryArtistMinimal": ["53d3f76582c49ad0a05dc685955f20dc2a5f2209b192e5446e5e4e623ce23a48"],
    "queryArtistDiscographyAll": ["5e07d323febb57b4a56a42abbf781490e58764aa45feb6e3dc0591564fc56599"],
    "queryArtistDiscographyAlbums": ["5e07d323febb57b4a56a42abbf781490e58764aa45feb6e3dc0591564fc56599"],
    "queryArtistDiscographySingles": ["5e07d323febb57b4a56a42abbf781490e58764aa45feb6e3dc0591564fc56599"],
    "queryArtistDiscographyCompilations": ["5e07d323febb57b4a56a42abbf781490e58764aa45feb6e3dc0591564fc56599"],
    "queryArtistDiscographyOverview": ["5e07d323febb57b4a56a42abbf781490e58764aa45feb6e3dc0591564fc56599"],
    "queryArtistRelated": ["3d031d6cb22a2aa7c8d203d49b49df731f58b1e2799cc38d9876d58771aa66f3"],
    "queryArtistAppearsOn": ["9a4bb7a20d6720fe52d7b47bc001cfa91940ddf5e7113761460b4a288d18a4c1"],
    "queryArtistDiscoveredOn": ["71c2392e4cecf6b48b9ad1311ae08838cbdabcfd189c6bf0c66c2430b8dcfdb1"],
    "queryArtistFeaturing": ["20842d6d9d2d28ef945984b68cb927bb33edd00eab84a8da1667def21f1f2c54"],
    "queryArtistPlaylists": ["54f7e5a5a2af05b7dc98526df376a46c6b15c05440c8dfdc8f6cecb1a807eca7"],
    "ArtistConcerts": ["ef53c43b865496b9890b7167eab1dc614a8949ef9451b3c41184ea888de8bd2b"],
    # playlists
    "fetchPlaylist": ["86dde7b9d9356e2369414647cf6950cfed96e778e129cfdfc99aea6c1613b3b0"],
    "fetchPlaylistMetadata": ["86dde7b9d9356e2369414647cf6950cfed96e778e129cfdfc99aea6c1613b3b0"],
    "fetchPlaylistContents": ["86dde7b9d9356e2369414647cf6950cfed96e778e129cfdfc99aea6c1613b3b0"],
    # podcasts / audiobooks
    "getEpisodeOrChapter": ["3416929067571ac4b79db16716be3c6ea5f6265f7975a0ee94b1fc5ee1dc1e9d"],
    "queryShowMetadataV2": ["40202837452991ffa80ced96987bc1a937e21d5a89df5bf1fb743110e4d6e93a"],
    "queryPodcastEpisodes": ["06046f9b939d56c8eb7cdbb687da938de1164c006871aec91dc26e4dc7d8eb08"],
    "getAudiobooksMetadata": ["523c71c64749a628f83e6b31a122c76663243730bf02df01fd64abf0f62f572f"],
    "queryBookChapters": ["8f342d1c624755901657fa65cbb80dd3bacbcca2f6d802f570ae3269d59a403e"],
    # search
    "searchDesktop": ["1148393611bbc58e84e47aed35ecc731275df9f9eb660956962e352dd3631d89"],
    "searchSuggestions": ["b50ebd72524415b132ddaca04158fd7aca529da28be322c9924643c0633df5bd"],
    "searchTracks": ["b02683192a98dde7966b5e6655a79eeb62713eab703eda9902c932818dd52751"],
    "searchAlbums": ["202cb3305e31e5a0767ba7925f28bd728cf8f8b0217e6da43909056071cd70e9"],
    "searchArtists": ["7bf95d754fdbe32c8b161fbbe54d1ae50974900df4dce4c8f1afcbcad153224d"],
    "searchPlaylists": ["d520014e748f9ea44f7707d8df1819867ac1205e8b7f3e28f22fe5fc858921b1"],
    "searchPodcasts": ["0195d9f61b43606d490bca64c3456e3593528cea6cc05c7e822c7c42beed0f4e"],
    "searchEpisodes": ["c9ee277c533bd3f191f9f09bee04f8e4e81bdc48f4d2fadbf67e504c75dc3fe1"],
    "searchAudiobooks": ["e05ac765d02c084f8783d3c1572b23d57761c43f47eb8b87ce2f9ccced3fa068"],
    "searchGenres": ["9e1c0e056c46239dd1956ea915b988913c87c04ce3dadccdb537774490266f46"],
    "searchUsers": ["8f358dd82e62f61dd4ceaa9f8cd0889e644c9b707f1b724fbfb356a757cb7e5a"],
    # browse / home
    "browseAll": ["dbd8b55e09a58afc52eab438bc228ba28fd72ac2f2148c6c26354980e4579001"],
    "browsePage": ["f5c4e6d668f5716464a231c1cc8b22c1cbf6ad68b09929fd7de813a30581298b"],
    "browseSection": ["b13c1cccbfcb6947753c2613411b3566485c21fd5f36d80a80bb64be61ba2d51"],
    "home": ["76243c78b0e20ecdbe41b794dec8cbe73f75e585b0a7201b8d2e84578412847a"],
    "countryHubsPage": ["6c2e4b04d8836507c2ad09c954f27a6c98d8b0a761f99ef6f4dc9bbe7834ba55",
                        "39093e27acf683e5906d0e8f49dc55ba3c037806381951e6afc95b9aa35f9312"],
    # users
    "queryUser": ["5b1399f199da0b45e368dac387ed4688e84a1c59111c835d0776e3a59d8a4395"],
    # concerts
    "concertFeed": ["9cae2dbee3f47904c60bab45256260b3ddb9844d5ef25038c17112619d14ce9a",
                    "4d5f059c15044b6199daf274f63d7a343b522befd79b67eea21bf5a26ac203a1"],
    "searchConcertLocations": ["43ededefcba8b3f519fd0c2d6c025dfeec9f742cf47d04a3c3711d95b27deda3"],
    "concert": ["edf8e3fd8c44c02047eb2ffb4e36ef44f884fa5a0c48d6a73645697eddddf40b",
                "1bf1ec3eef97e42fce6394cb86c188e397cc226151a9c110dc0840a2d020edd2"],
    "venue": ["6c55ebc91fc13a25d7df590c4a9031dd1dcdc25716192d7f848a8270f49d2c13",
              "75cc2d2d7b494137e8e2ebc414f9f7f6d79330a2de645ab275b6c51a7f3566f7"],
}

# The `*EndUserIntegration` enum every browse/home query wants (raw token,
# not a string — the gateway rejects a quoted value).
WEB_PLAYER_INTEGRATION = "INTEGRATION_WEB_PLAYER"

# Flags every search operation takes besides searchTerm/offset/limit.
SEARCH_FLAGS = {
    "numberOfTopResults": 5,
    "includeAudiobooks": True,
    "includeArtistHasConcertsField": False,
    "includePreReleases": True,
    "includeLocalConcertsField": False,
    "includeAuthors": True,
}
