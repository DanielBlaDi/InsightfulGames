package com.prototipo.profile.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** Contadores de partidas multiplayer con resultado. Se modifican solo con StatsRepository.add. */
@Entity
@Table(name = "stats")
public class Stats {

    @Id
    @Column(name = "user_id", nullable = false, length = 36)
    private String userId;

    @Column(name = "games_played", nullable = false)
    private int gamesPlayed;

    @Column(name = "wins", nullable = false)
    private int wins;

    @Column(name = "losses", nullable = false)
    private int losses;

    @Column(name = "draws", nullable = false)
    private int draws;

    protected Stats() {
        // Constructor requerido por JPA.
    }

    public Stats(String userId) {
        this.userId = userId;
    }

    public String getUserId() {
        return userId;
    }

    public int getGamesPlayed() {
        return gamesPlayed;
    }

    public int getWins() {
        return wins;
    }

    public int getLosses() {
        return losses;
    }

    public int getDraws() {
        return draws;
    }
}
