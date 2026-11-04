package chess;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import chess.matches.GameLogicProperties;

@SpringBootApplication
@EnableConfigurationProperties(GameLogicProperties.class)
public class ChessApplication{
	public static void main(String[] args) {
		SpringApplication.run(ChessApplication.class, args);
	}
}