package com.prototipo.profile.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * Usuario cuya cuenta se borró. Tabla interna, fuera de la lista de v9: impide que un
 * user.registered tardío vuelva a crear el perfil.
 */
@Entity
@Table(name = "deleted_users")
public class DeletedUser {

    @Id
    @Column(name = "user_id", nullable = false, length = 36)
    private String userId;

    @Column(name = "deleted_at", nullable = false)
    private Instant deletedAt;

    protected DeletedUser() {
        // Constructor requerido por JPA.
    }

    public DeletedUser(String userId, Instant deletedAt) {
        this.userId = userId;
        this.deletedAt = deletedAt;
    }
}
