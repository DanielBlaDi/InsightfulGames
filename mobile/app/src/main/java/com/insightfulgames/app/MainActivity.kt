package com.insightfulgames.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.insightfulgames.app.ui.AppRoot
import com.insightfulgames.app.ui.theme.InsightfulTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            InsightfulTheme {
                AppRoot()
            }
        }
    }
}
