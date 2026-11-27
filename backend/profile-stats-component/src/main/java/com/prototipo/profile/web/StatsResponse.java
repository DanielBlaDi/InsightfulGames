package com.prototipo.profile.web;

/** GET /stats/me. Solo partidas multiplayer con resultado. */
public record StatsResponse(int gamesPlayed, int wins, int losses, int draws) {

    public static final StatsResponse EMPTY = new StatsResponse(0, 0, 0, 0);
}
