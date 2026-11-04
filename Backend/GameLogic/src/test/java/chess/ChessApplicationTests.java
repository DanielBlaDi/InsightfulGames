package chess;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

// Solo comprueba que el contexto se arma. Con auto-index-creation=true (application.properties)
// Spring crearía los índices al arrancar y necesitaría un MongoDB en marcha; aquí no hace falta.
@SpringBootTest(properties = "spring.data.mongodb.auto-index-creation=false")
class ChessApplicationBasicTests{
	@Test
	void contextLoads(){}
}
