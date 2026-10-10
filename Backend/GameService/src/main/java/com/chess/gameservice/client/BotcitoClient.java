package com.chess.gameservice.client;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Cliente REST de Botcito (tarea 8, Python + Stockfish).
 * Contrato propuesto (confirmar con el dueño de la tarea 8):
 *   POST /best-move   {"fen": "...", "level": 1-20}   ->   {"move": "e7e5"}
 */
@Component
public class BotcitoClient {

    public record BestMoveRequest(String fen, int level) {}

    public record BestMoveResponse(String move) {}

    private final RestClient http;
    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();

    public BotcitoClient(@Value("${botcito.url}") String baseUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(3000);
        factory.setReadTimeout(15000);
        this.http = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
    }

    public CompletableFuture<String> bestMove(String fen, int level) {
        return CompletableFuture.supplyAsync(() -> {
            BestMoveResponse response = http.post()
                    .uri("/best-move")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new BestMoveRequest(fen, level))
                    .retrieve()
                    .body(BestMoveResponse.class);
            if (response == null || response.move() == null) {
                throw new IllegalStateException("Respuesta vacía de Botcito");
            }
            return response.move();
        }, executor);
    }
}
