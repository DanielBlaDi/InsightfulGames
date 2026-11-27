package com.prototipo.auth.outbox;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;

public interface OutboxRepository extends JpaRepository<OutboxEvent, String> {

    /** Pendientes, del más antiguo al más reciente, para publicarlos en orden. */
    List<OutboxEvent> findTop50ByPublishedAtIsNullOrderByCreatedAtAsc();

    long countByPublishedAtIsNull();

    @Transactional
    @Modifying
    @Query("delete from OutboxEvent e where e.publishedAt is not null and e.publishedAt < :before")
    int deletePublishedBefore(@Param("before") Instant before);
}
