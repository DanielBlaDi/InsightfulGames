package com.prototipo.auth.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.UUID;

@Entity
@Table(name = "users")
public class User {

    @Id
    @Column(name = "user_id", nullable = false, length = 36)
    private String userId;

    @Column(name = "username", nullable = false, unique = true, length = 20)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    protected User() {
        // Constructor requerido por JPA.
    }

    public User(String username, String passwordHash) {
        this.userId = UUID.randomUUID().toString();
        this.username = username;
        this.passwordHash = passwordHash;
    }

    public String getUserId() {
        return userId;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }
}
