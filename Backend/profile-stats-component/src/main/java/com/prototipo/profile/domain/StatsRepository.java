package com.prototipo.profile.domain;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface StatsRepository extends JpaRepository<Stats, String> {

    /** Suma una partida en una sola sentencia, sin leer antes: no pierde actualizaciones. */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update Stats s
               set s.gamesPlayed = s.gamesPlayed + 1,
                   s.wins = s.wins + :wins,
                   s.losses = s.losses + :losses,
                   s.draws = s.draws + :draws
             where s.userId = :userId
            """)
    int add(@Param("userId") String userId, @Param("wins") int wins,
            @Param("losses") int losses, @Param("draws") int draws);
}
