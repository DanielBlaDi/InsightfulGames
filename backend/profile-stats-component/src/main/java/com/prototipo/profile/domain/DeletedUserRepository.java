package com.prototipo.profile.domain;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DeletedUserRepository extends JpaRepository<DeletedUser, String> {
}
